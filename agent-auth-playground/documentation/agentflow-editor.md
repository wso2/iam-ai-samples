# AgentFlow Editor

The AgentFlow Editor is the main canvas where you design AgentFlows by placing and connecting nodes.

---

## Toolbar

| Button | What it does |
|--------|--------------|
| **+ Chat Trigger** | Add a Chat Trigger node (disabled once one exists) |
| **+ AI Agent** | Add an AI Agent node (disabled once one exists) |
| **+ AI Service** | Add an AI Service (LLM) node (disabled once one exists) |
| **+ MCP Client** | Add an MCP Client node (multiple allowed) |
| **Delete Node** | Delete the selected node — only shown when a node is selected |

New nodes are placed at a random position on the canvas. Drag them to rearrange.

Node configuration opens in a **modal dialog** when you double-click a node.

---

## Selecting and Configuring Nodes

**Single click** — selects the node. The **Delete Node** button becomes active in the toolbar.

**Double-click** — opens the node's configuration in a modal dialog.

**Click on empty canvas** — deselects the current node.

---

## Creating Connections

1. Hover over a node until small plus sign appear on its edges.
2. Click and drag from a **source** handle to a **target** handle on another node.
3. Release to create the connection. An animated edge will appear.

The canvas enforces connection rules — invalid connections are silently rejected.

### Connection Rules

| From node | From handle | To node | To handle |
|-----------|-------------|---------|-----------|
| Chat Trigger | Right | AI Agent | Left |
| AI Agent | Top | AI Service | Bottom |
| AI Agent | Right | MCP Client | Left |

**1:1 constraints**: Chat Trigger and AI Agent each allow only one connection between them. AI Agent allows only one AI Service connection. An AI Agent can connect to multiple MCP Client nodes.

---


## Chat Panel

The chat panel overlays the left side of the canvas. To get more canvas space:

- Click the **×** (hide) button at the top of the chat panel — the panel slides away
- A **Show Chat** button appears at the bottom-left of the canvas to bring it back

---

## Managing AgentFlows

AgentFlow state is auto-saved to browser localStorage as you work. Use the **⋮** dropdown next to the AgentFlow name for the following actions.

### Download and Import

- **Download** — exports the current AgentFlow as a `.json` file.
- **Import** — loads an AgentFlow from a `.json` file, replacing the current canvas.

### Start Fresh

**Start Fresh** resets the canvas to a new default AgentFlow and clears all associated data, But your saved LLM and agent credentials are preserved.

### Naming an AgentFlow

Edit the AgentFlow name directly in the name field in the toolbar. Changes are auto-saved.