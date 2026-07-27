# 0003 — Use WebView2 instead of Qt for the desktop shell

Date: 2026-07-28
Status: accepted

## Context

The first desktop draft used PySide6. Installing its Essentials and Addons
packages added roughly 250 MB before application models or the Python runtime.
The product is a focused, single-window workflow and the user explicitly
preferred a lighter interface technology.

## Decision

Use pywebview on Windows with the system Edge WebView2 Evergreen Runtime:

- bundled local HTML, CSS, and JavaScript only;
- no CDN, remote fonts, frontend framework, or Node runtime;
- an allow-listed JavaScript-to-Python API;
- the existing Python model pipeline remains in-process;
- inference runs in one dedicated worker thread;
- WebView2 is detected by the installer and the offline standalone installer is
  offered only when the runtime is absent.

Tauri was considered but rejected for v0.1. It would still require packaging
the complete Python inference runtime as a sidecar while adding Rust IPC and
process-lifecycle coordination.

## Consequences

- The release does not ship Qt or a browser engine.
- Windows 11 already includes the Evergreen WebView2 Runtime. The installer
  must handle the minority of Windows 10 systems where it is absent.
- The API object must not expose public object-graph attributes because
  pywebview recursively exposes public members. Only explicit methods cross the
  bridge.
- Frontend assets use a restrictive Content Security Policy and never load
  network content.
- PyInstaller must explicitly exclude Qt packages if they are present in the
  build environment.

## Evidence

- pywebview introduction:
  https://pywebview.idepy.com/en/guide/
- pywebview JavaScript/Python bridge:
  https://pywebview.idepy.com/en/guide/interdomain
- pywebview freezing guidance:
  https://pywebview.idepy.com/guide/freezing
- Microsoft WebView2 distribution:
  https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
