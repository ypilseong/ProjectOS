# ProjectOS Vault Sync Obsidian Plugin

This plugin connects a local Obsidian vault to a ProjectOS backend.

It is the Mac integration layer. A separate native macOS app is not required:
Obsidian is already the desktop app, and this plugin runs inside Obsidian with
direct access to the local vault.

## Features

- Sync generated ProjectOS vault payloads into the local vault.
- Create or select ProjectOS backend projects without manually remembering ids.
- View backend projects directly in the side panel and select one from the visible list.
- Select backend runtime mode from the side panel or plugin settings:
  - `Local`: local OpenAI-compatible endpoint
  - `Hybrid`: local graph extraction with Claude Code maintenance
  - `Claude Task`: isolated Claude Code graph build flow
- Upload files to a ProjectOS project and trigger graph build.
- Ask questions through ProjectOS `QueryAgent` and stream answers in the side panel.
- Run ProjectOS document analysis and view summary, improvement points, and improved draft.

## Build

```bash
npm install
npm run build
```

## Manual Install On Mac

1. Open the target vault in Obsidian.
2. Create:

   ```text
   <vault>/.obsidian/plugins/projectos-vault-sync/
   ```

3. Copy these files into that folder:

   ```text
   manifest.json
   main.js
   styles.css
   ```

4. In Obsidian, enable Community plugins and turn on `ProjectOS Vault Sync`.
5. Open plugin settings and set:
   - Backend base URL: `http://<server-host>:8002`
   - Target folder: optional folder inside the vault, e.g. `ProjectOS`

Project ID does not need to be typed manually. Open the ProjectOS side panel and
use `Create project` or `Refresh` + project selector. The plugin stores the
selected backend project id automatically.

If target folder is empty, each project syncs into:

```text
ProjectOS/<project name>/
```

That lets multiple ProjectOS projects appear together in Obsidian Graph View
while keeping generated files separated by project.

## Backend Requirements

The ProjectOS backend must expose:

- `GET /api/projects/{project_id}/vault/export`
- `POST /api/projects/{project_id}/files`
- `POST /api/projects/{project_id}/graph`
- `GET /api/tasks/{task_id}/stream`
- `POST /api/projects/{project_id}/chat`

The backend CORS configuration already includes Obsidian origins.

Runtime mode selection uses:

- `GET /api/settings`
- `POST /api/settings`
