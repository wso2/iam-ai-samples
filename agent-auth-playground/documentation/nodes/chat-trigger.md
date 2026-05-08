# Chat Trigger

The Chat Trigger is the entry point of every AgentFlow. It receives the message you type in the chat panel and passes it to the next connected node.

---

## At a Glance

- Every AgentFlow must have exactly one Chat Trigger.
- It has no configuration options — just add it and connect it.
- Connect it to an **AI Agent** using the handle on its right side.

---

## How to Use It

1. Click **+ Chat Trigger** in the toolbar.
2. Drag from its **right handle** to the **left handle** of an AI Agent node.

That's it. When you send a message in the chat panel, the Chat Trigger receives it and kicks off the rest of the AgentFlow.

---

## Connection

| Handle | Direction | Connects to |
|--------|-----------|-------------|
| Right | Output | AI Agent |

The Chat Trigger only outputs - it cannot receive connections from other nodes.

---