export default function ChatTriggerPanel() {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-semibold text-gray-700 mb-1">About</p>
        <p className="text-sm text-gray-600">
          This node receives messages from the chat interface and passes them to
          the next node in the workflow.
        </p>
      </div>
    </div>
  );
}
