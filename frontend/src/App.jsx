import { useState } from 'react';

export default function App() {
  const [count, setCount] = useState(0);

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col items-center justify-center p-6">
      <h1 className="text-4xl font-bold tracking-tight text-center mb-6">
        E-Commerce AI Customer Support
      </h1>
      <button
        onClick={() => setCount((c) => c + 1)}
        className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white transition-colors duration-200 hover:bg-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-300 dark:focus:ring-blue-800"
      >
        Count is {count}
      </button>
    </div>
  );
}
