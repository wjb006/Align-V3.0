//go:build windows

package main

import (
	"syscall"
	"unsafe"
)

func showMessage(text string) {
	user32 := syscall.NewLazyDLL("user32.dll")
	messageBox := user32.NewProc("MessageBoxW")
	body, err := syscall.UTF16PtrFromString(text)
	if err != nil {
		return
	}
	title, err := syscall.UTF16PtrFromString("Align Studio")
	if err != nil {
		return
	}
	const mbIconError = 0x00000010
	messageBox.Call(0, uintptr(unsafe.Pointer(body)), uintptr(unsafe.Pointer(title)), mbIconError)
}
