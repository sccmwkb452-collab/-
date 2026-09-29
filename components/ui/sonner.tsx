"use client";

import { Toaster as Sonner } from "sonner";

function Toaster() {
  return (
    <Sonner
      position="top-center"
      toastOptions={{
        classNames: {
          toast: "!rounded-2xl !border-border !bg-card !text-foreground !shadow-xl !font-sans",
          description: "!text-muted-foreground",
        },
      }}
    />
  );
}

export { Toaster };
