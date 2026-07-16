# ProjectOS Vault Sync Obsidian Plugin

Thin Obsidian integration for ProjectOS.

Claude Desktop and ProjectOS MCP handle project creation, ingestion, graph
builds, review, and simulation. This plugin only pulls a built ProjectOS vault
export into the local Obsidian vault.

## Features

- List backend projects.
- Select one project.
- Sync the generated vault export into a local Obsidian folder.

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
   - Backend base URL: `http://localhost:14006`
   - Target folder: optional folder inside the vault, e.g. `ProjectOS`

For an SSH server, open this tunnel on the Mac before syncing:

```bash
ssh -N -L 14006:127.0.0.1:14006 projectos-server
```

If target folder is empty, each project syncs into:

```text
ProjectOS/<project name>/
```

## Backend Requirements

The ProjectOS backend must expose:

- `GET /api/projects`
- `GET /api/projects/{project_id}/vault/export`
