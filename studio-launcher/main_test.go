package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestHealthyLocalAlign(t *testing.T) {
	if !healthy("8001") {
		t.Skip("Align is not answering on port 8001")
	}
	if healthy("59999") {
		t.Fatal("an unused port was reported as healthy")
	}
}

func TestPythonLaunchUsesInstallVenv(t *testing.T) {
	dir := t.TempDir()
	pythonPath := filepath.Join(dir, ".venv", "bin", "python")
	if runtime.GOOS == "windows" {
		pythonPath = filepath.Join(dir, ".venv", "Scripts", "pythonw.exe")
	}
	if err := os.MkdirAll(filepath.Dir(pythonPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(pythonPath, []byte(""), 0o755); err != nil {
		t.Fatal(err)
	}
	python, args := pythonLaunch(dir)
	if strings.Join(args, " ") != "-m desktop" {
		t.Fatalf("args = %v", args)
	}
	if python != pythonPath {
		t.Fatalf("python = %s", python)
	}
}

func TestPythonLaunchSupportsPackagedAppDirectory(t *testing.T) {
	dir := t.TempDir()
	appDir := filepath.Join(dir, "app")
	pythonPath := filepath.Join(dir, ".venv", "bin", "python")
	if runtime.GOOS == "windows" {
		pythonPath = filepath.Join(dir, ".venv", "Scripts", "pythonw.exe")
	}
	if err := os.MkdirAll(appDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(appDir, "app.py"), []byte(""), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(pythonPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(pythonPath, []byte(""), 0o755); err != nil {
		t.Fatal(err)
	}
	python, args := pythonLaunch(dir)
	if python != pythonPath {
		t.Fatalf("python = %s", python)
	}
	if strings.Join(args, " ") != "-m desktop" {
		t.Fatalf("args = %v", args)
	}
	if applicationDir(dir) != appDir {
		t.Fatalf("applicationDir = %s", applicationDir(dir))
	}
}

func TestHealthStatusRecognizesAlignAndRejectsOtherServices(t *testing.T) {
	for _, test := range []struct {
		name     string
		body     string
		expected bool
	}{
		{name: "Align", body: `{"version":{"build":156,"app":"3.0"}}`, expected: true},
		{name: "other service", body: `{"status":"ok"}`},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_, _ = w.Write([]byte(test.body))
			}))
			defer server.Close()
			port := strings.TrimPrefix(server.URL, "http://127.0.0.1:")
			ready, responding := healthStatus(port)
			if ready != test.expected || !responding {
				t.Fatalf("healthStatus = (%t, %t), expected ready=%t and responding=true", ready, responding, test.expected)
			}
		})
	}
}

func TestWindowsAppWindowIsLarge(t *testing.T) {
	browser := firstExisting([]string{"/missing", "/edge"}, func(path string) bool { return path == "/edge" })
	command, args := commandForBrowser("http://127.0.0.1:8001/management-studio", browser)
	if command != "/edge" {
		t.Fatalf("command = %s", command)
	}
	joined := strings.Join(args, "\n")
	if !strings.Contains(joined, "--window-size=1360,900") || !strings.Contains(joined, "--app=http://127.0.0.1:8001/management-studio") {
		t.Fatalf("args = %v", args)
	}
}

func TestDataDirectoryUsesTheOverride(t *testing.T) {
	t.Setenv("ALIGN_DATA_DIR", filepath.Join(t.TempDir(), "kept"))
	if dataDirectory() != os.Getenv("ALIGN_DATA_DIR") {
		t.Fatalf("dataDirectory = %s", dataDirectory())
	}
}

func TestLaunchActionPrefersAnExistingAlign(t *testing.T) {
	if launchAction(true, true) != "open" || launchAction(true, false) != "open" {
		t.Fatal("a healthy Align should be opened, not started again")
	}
	if launchAction(false, true) != "blocked" {
		t.Fatal("another programme on the port should block launch")
	}
	if launchAction(false, false) != "start" {
		t.Fatal("a free port should start the desktop programme")
	}
}

func TestProgrammeArgsLeaveTheWindowToTheLauncher(t *testing.T) {
	args := programmeArgs([]string{"-m", "desktop"})
	if strings.Join(args, " ") != "-m desktop --no-browser" {
		t.Fatalf("args = %v", args)
	}
}

func TestWindowsAppWindowFallsBackToTheDefaultBrowser(t *testing.T) {
	command, args := commandForBrowser("http://127.0.0.1:8001/management-studio", "")
	if command != "rundll32" {
		t.Fatalf("command = %s", command)
	}
	if len(args) != 2 || args[0] != "url.dll,FileProtocolHandler" {
		t.Fatalf("args = %v", args)
	}
}
