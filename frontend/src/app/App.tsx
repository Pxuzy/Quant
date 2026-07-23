import { RouterProvider } from '@tanstack/react-router';
import { router } from './router';
import '../shared/styles/tradingview.css';

export function App() {
  return <RouterProvider router={router} />;
}
