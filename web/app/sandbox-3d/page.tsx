'use client';

import dynamic from 'next/dynamic';
import React, { useEffect, useState } from 'react';
import type { SupervisorPayload } from '@/lib/types';
import { getJson } from '@/lib/api';

// Force client-side rendering for the 3D canvas due to WebGL/Window dependencies
const Site3DLab = dynamic(() => import('@/components/site-3d-lab/Site3DLab'), {
  ssr: false,
  loading: () => (
    <div className="flex w-full h-[calc(100vh-68px)] items-center justify-center bg-[#0c120e] text-emerald-400 font-mono text-sm tracking-wider">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"></div>
        <span>INITIALIZING 3D ENVIRONMENT...</span>
      </div>
    </div>
  ),
});

export default function Sandbox3DPage() {
  const [payload, setPayload] = useState<SupervisorPayload | null>(null);

  useEffect(() => {
    let alive = true;
    getJson<SupervisorPayload>('/api/supervisor?scenario=replay&reading=aligned')
      .then((data) => {
        if (alive) setPayload(data);
      })
      .catch((err) => {
        console.warn('Sandbox 3D: Using fallback baseline state', err);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <main className="w-full">
      <Site3DLab payload={payload} />
    </main>
  );
}
