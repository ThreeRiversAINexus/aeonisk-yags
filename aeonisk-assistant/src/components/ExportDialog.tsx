interface ExportDialogProps {
  onExport: (format: 'jsonl' | 'finetune' | 'assistant' | 'sharegpt') => void;
  onClose: () => void;
}

export function ExportDialog({ onExport, onClose }: ExportDialogProps) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <h2 className="text-xl font-bold mb-4">Export Conversation</h2>
        
        <div className="space-y-2">
          <button
            onClick={() => onExport('jsonl')}
            className="w-full text-left px-4 py-3 bg-gray-700 rounded hover:bg-gray-600 transition-colors"
          >
            <div className="font-medium">JSONL Format</div>
            <div className="text-sm text-gray-400">OpenAI-compatible format for general use</div>
          </button>
          
          <button
            onClick={() => onExport('finetune')}
            className="w-full text-left px-4 py-3 bg-gray-700 rounded hover:bg-gray-600 transition-colors"
          >
            <div className="font-medium">Fine-tuning Format</div>
            <div className="text-sm text-gray-400">Only includes highly-rated exchanges</div>
          </button>
          
          <button
            onClick={() => onExport('assistant')}
            className="w-full text-left px-4 py-3 bg-gray-700 rounded hover:bg-gray-600 transition-colors"
          >
            <div className="font-medium">Assistants API Format</div>
            <div className="text-sm text-gray-400">OpenAI Assistants thread format</div>
          </button>
          
          <button
            onClick={() => onExport('sharegpt')}
            className="w-full text-left px-4 py-3 bg-gray-700 rounded hover:bg-gray-600 transition-colors"
          >
            <div className="font-medium">ShareGPT Format</div>
            <div className="text-sm text-gray-400">Compatible with ShareGPT tools</div>
          </button>
        </div>
        
        <button
          onClick={onClose}
          className="mt-4 w-full px-4 py-2 bg-gray-600 rounded hover:bg-gray-500 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
