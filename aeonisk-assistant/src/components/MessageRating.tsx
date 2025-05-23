import { useState } from 'react';

interface MessageRatingProps {
  onRate: (rating: 'good' | 'bad' | 'edit') => void;
}

export function MessageRating({ onRate }: MessageRatingProps) {
  const [hasRated, setHasRated] = useState(false);

  const handleRate = (rating: 'good' | 'bad' | 'edit') => {
    onRate(rating);
    setHasRated(true);
  };

  if (hasRated) {
    return (
      <div className="mt-2 text-xs text-gray-500">
        Thanks for your feedback!
      </div>
    );
  }

  return (
    <div className="mt-2 flex gap-2">
      <button
        onClick={() => handleRate('good')}
        className="text-xs text-gray-400 hover:text-green-400 transition-colors"
        title="Good response"
      >
        👍
      </button>
      <button
        onClick={() => handleRate('bad')}
        className="text-xs text-gray-400 hover:text-red-400 transition-colors"
        title="Bad response"
      >
        👎
      </button>
      <button
        onClick={() => handleRate('edit')}
        className="text-xs text-gray-400 hover:text-yellow-400 transition-colors"
        title="Edit response"
      >
        ✏️
      </button>
    </div>
  );
}
