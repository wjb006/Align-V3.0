// Align desktop launcher.
// It starts the Python desktop programme, which opens Planner and Management Studio.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
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
	homeURL := "http://127.0.0.1:" + port + "/desktop"
	python, args := pythonLaunch(dir)
	if *dryRun {
		fmt.Printf("start %s %s\n", python, strings.Join(args, " "))
		fmt.Println("open", homeURL)
		return
	}
	if err := startServer(dir, python, args); err != nil {
		fail(fmt.Errorf("Align could not start. Install Python 3.12, or use the packaged Align.exe. %s", err))
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
	ready, _ := healthStatus(port)
	return ready
}

func healthStatus(port string) (bool, bool) {
	client := http.Client{Timeout: 2 * time.Second}
	response, err := client.Get("http://127.0.0.1:" + port + "/api/health")
	if err != nil {
		return false, false
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return false, true
	}
	var payload struct {
		Version struct {
			Build int    `json:"build"`
			App   string `json:"app"`
		} `json:"version"`
	}
	if err := json.NewDecoder(io.LimitReader(response.Body, 64*1024)).Decode(&payload); err != nil {
		return false, true
	}
	return payload.Version.Build > 0 && payload.Version.App == "3.0", true
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

func pythonLaunch(dir string) (string, []string) {
	args := []string{"-m", "desktop"}
	if runtime.GOOS == "windows" {
		python := filepath.Join(dir, ".venv", "Scripts", "pythonw.exe")
		if _, err := os.Stat(python); err != nil {
			python = "pythonw.exe"
		}
		return python, args
	}
	python := filepath.Join(dir, ".venv", "bin", "python")
	if _, err := os.Stat(python); err != nil {
		python = "python3"
	}
	return python, args
}

func dataDirectory() string {
	if value := strings.TrimSpace(os.Getenv("ALIGN_DATA_DIR")); value != "" {
		return value
	}
	if runtime.GOOS == "windows" {
		base := os.Getenv("LOCALAPPDATA")
		if base == "" {
			base = filepath.Join(os.Getenv("USERPROFILE"), "AppData", "Local")
		}
		return filepath.Join(base, "Align")
	}
	if base := os.Getenv("XDG_DATA_HOME"); base != "" {
		return filepath.Join(base, "align")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		home = ""
	}
	return filepath.Join(home, ".local", "share", "align")
}

func commandEnv() []string {
	env := os.Environ()
	if strings.TrimSpace(os.Getenv("ALIGN_DATA_DIR")) == "" {
		env = append(env, "ALIGN_DATA_DIR="+dataDirectory())
	}
	if strings.TrimSpace(os.Getenv("ALIGN_STUDIO_LOCAL")) == "" {
		env = append(env, "ALIGN_STUDIO_LOCAL=1")
	}
	return env
}

func applicationDir(dir string) string {
	nested := filepath.Join(dir, "app")
	if info, err := os.Stat(filepath.Join(nested, "app.py")); err == nil && !info.IsDir() {
		return nested
	}
	return dir
}

func startServer(dir, python string, args []string) error {
	command := exec.Command(python, args...)
	command.Dir = applicationDir(dir)
	command.Env = commandEnv()
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
