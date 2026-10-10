// Align Management Studio launcher.
// It starts the local Align server in this folder when it is not already
// running, then opens Management Studio in the browser.
package main

import (
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"
)

func main() {
	dryRun := flag.Bool("dry-run", false, "print the launch actions without starting Align or a browser")
	flag.Parse()

	dir, err := installDir()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	port := os.Getenv("ALIGN_PORT")
	if port == "" {
		port = "8001"
	}
	studioURL := "http://127.0.0.1:" + port + "/management-studio"
	if !healthy(port) {
		python, args := pythonLaunch(dir)
		if *dryRun {
			fmt.Printf("start %s %s\n", python, args)
		} else if err := startServer(dir, python, args); err != nil {
			fail(err)
		}
		if !*dryRun && !waitHealthy(port, 30*time.Second) {
			fail(fmt.Errorf("Align Studio could not open. Check that Python is installed, then try again. Port %s did not answer.", port))
		}
	} else if *dryRun {
		fmt.Printf("already running on %s\n", port)
	}
	if *dryRun {
		fmt.Println("open", studioURL)
		return
	}
	if err := openBrowser(studioURL); err != nil {
		fail(fmt.Errorf("Align Studio could not open a window. Open %s in your browser.", studioURL))
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	showMessage(err.Error())
	os.Exit(1)
}

func installDir() (string, error) {
	executable, err := os.Executable()
	if err != nil {
		return "", err
	}
	resolved, err := filepath.EvalSymlinks(executable)
	if err != nil {
		resolved = executable
	}
	return filepath.Dir(resolved), nil
}

func healthy(port string) bool {
	client := http.Client{Timeout: 2 * time.Second}
	response, err := client.Get("http://127.0.0.1:" + port + "/api/health")
	if err != nil {
		return false
	}
	defer response.Body.Close()
	return response.StatusCode == http.StatusOK
}

func waitHealthy(port string, limit time.Duration) bool {
	deadline := time.Now().Add(limit)
	for time.Now().Before(deadline) {
		if healthy(port) {
			return true
		}
		time.Sleep(500 * time.Millisecond)
	}
	return healthy(port)
}

func pythonLaunch(dir string) (string, string) {
	launch := filepath.Join(dir, "launch.py")
	if runtime.GOOS == "windows" {
		python := filepath.Join(dir, ".venv", "Scripts", "pythonw.exe")
		if _, err := os.Stat(python); err != nil {
			python = "pythonw.exe"
		}
		return python, launch
	}
	python := filepath.Join(dir, ".venv", "bin", "python")
	if _, err := os.Stat(python); err != nil {
		python = "python3"
	}
	return python, launch
}

func startServer(dir, python, launch string) error {
	command := exec.Command(python, launch)
	command.Dir = dir
	return command.Start()
}

func windowsBrowserCandidates() []string {
	var paths []string
	for _, root := range []string{os.Getenv("ProgramFiles(x86)"), os.Getenv("ProgramFiles"), os.Getenv("LocalAppData")} {
		if root == "" {
			continue
		}
		paths = append(paths,
			filepath.Join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
			filepath.Join(root, "Google", "Chrome", "Application", "chrome.exe"),
		)
	}
	return paths
}

func firstExisting(paths []string, exists func(string) bool) string {
	for _, path := range paths {
		if exists(path) {
			return path
		}
	}
	return ""
}

func commandForBrowser(url, browser string) (string, []string) {
	if browser == "" {
		return "rundll32", []string{"url.dll,FileProtocolHandler", url}
	}
	return browser, []string{"--app=" + url, "--window-size=1360,900", "--new-window"}
}

func appWindowCommand(url string, exists func(string) bool) (string, []string) {
	switch runtime.GOOS {
	case "windows":
		return commandForBrowser(url, firstExisting(windowsBrowserCandidates(), exists))
	case "darwin":
		return "open", []string{url}
	default:
		return "xdg-open", []string{url}
	}
}

func openBrowser(url string) error {
	command, args := appWindowCommand(url, func(path string) bool {
		info, err := os.Stat(path)
		return err == nil && !info.IsDir()
	})
	return exec.Command(command, args...).Start()
}
