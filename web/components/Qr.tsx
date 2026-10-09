"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";

export function Qr({
  value,
  size = 148,
  alt,
  quietZone = 2,
}: {
  value: string;
  size?: number;
  alt: string;
  quietZone?: number;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    QRCode.toDataURL(value, {
      errorCorrectionLevel: "M",
      margin: quietZone,
      width: size,
      color: { dark: "#0B0F14", light: "#E7EEF5" },
    })
      .then((url) => {
        if (live) setSrc(url);
      })
      .catch(() => {
        if (live) setSrc(null);
      });
    return () => {
      live = false;
    };
  }, [value, size, quietZone]);

  if (!src) {
    return (
      <div
        style={{ width: size, height: size }}
        className="animate-pulse border border-rule bg-concrete-700"
        aria-hidden
      />
    );
  }
  return <img src={src} width={size} height={size} alt={alt} className="block" />;
}
