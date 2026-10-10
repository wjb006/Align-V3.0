package main

import (
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
	python, launch := pythonLaunch(dir)
	if filepath.Base(launch) != "launch.py" {
		t.Fatalf("launch = %s", launch)
	}
	if python != pythonPath {
		t.Fatalf("python = %s", python)
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

func TestWindowsAppWindowFallsBackToTheDefaultBrowser(t *testing.T) {
	command, args := commandForBrowser("http://127.0.0.1:8001/management-studio", "")
	if command != "rundll32" {
		t.Fatalf("command = %s", command)
	}
	if len(args) != 2 || args[0] != "url.dll,FileProtocolHandler" {
		t.Fatalf("args = %v", args)
	}
}
