import { LoaderCircle } from 'lucide-react';

export default function Spinner({ size = 18, className = '' }) {
  return <LoaderCircle size={size} className={`spin ${className}`} aria-hidden="true" />;
}
