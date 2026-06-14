"use client";

import { motion } from "framer-motion";

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-8"
    >
      <h1 className="text-3xl font-bold tracking-tight md:text-4xl">{title}</h1>
      {description && (
        <p className="mt-2 max-w-2xl text-muted-foreground">{description}</p>
      )}
    </motion.header>
  );
}
