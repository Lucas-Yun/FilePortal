# FilePortal v1.0.0

A lightweight, self-hosted file portal with role-based access, online preview, ZIP packaging, recycle bin, shared cloud folders, and a built-in Chinese/English interface.

## Downloads

| Platform | File | Notes |
|---|---|---|
| Windows 10/11 x64 | `FilePortal-Windows-x64.exe` | Single-file portable build. Double-click to start. Data is stored next to the executable. |
| Linux x86_64 | `FilePortal-Linux.zip` | Extract and run `./launcher.sh`. Requires Python 3.10+. |

SHA-256 checksums are published next to each asset.

## First run

1. Start the program.
2. Open `http://127.0.0.1:8000`.
3. Sign in as `Admin` with the initial password `ChangeMe_Admin`.
4. Change the password immediately in the admin panel.
5. Set the shared folder in **Admin → Settings** (portable builds default to `~/Documents/FilePortalShare`).

Only the `Admin` account is enabled by default in the packaged builds. Study/Read roles can be created from the admin panel after first login.

## Fixes in this build

- Mobile and tablet login layouts now stack cleanly instead of squeezing the login card and notice card side by side.
- Long “用户须知” content on the personal cloud page can scroll from the top without the first lines being clipped.
- The language switcher no longer overlays content on small or short screens.
- Windows portable EXE no longer returns an empty HTTP response when running without a console; request logging is safe when `sys.stderr` is unavailable.

## Documentation

- Setup, configuration, HTTPS, roles, and troubleshooting: `README.md`
- Security model and private vulnerability reporting: `SECURITY.md`
- Development, testing, and pull requests: `CONTRIBUTING.md`
- Community standards: `CODE_OF_CONDUCT.md`
- Version history: `CHANGELOG.md`

## Notes

- No personal contact information, user lists, block lists, or production passwords are bundled.
- All data stays in the local `app/data` and `app/runtime` folders.
- FilePortal is provided under the MIT License. See `LICENSE` for the full text and copyright notice.
