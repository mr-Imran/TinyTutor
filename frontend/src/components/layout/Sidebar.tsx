"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  BarChart3,
  BookOpen,
  BookMarked,
  Brain,
  Database,
  GraduationCap,
  LayoutGrid,
  LayoutDashboard,
  Settings,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/study", label: "What to Study", icon: BookMarked },
  { href: "/tutor", label: "AI Tutor", icon: Brain },
  { href: "/exam-hub", label: "Exam Hub", icon: LayoutGrid },
  { href: "/quiz", label: "Quiz Center", icon: GraduationCap },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/database", label: "Local DB", icon: Database },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      className="glass fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-white/10 p-4 md:relative md:h-auto md:min-h-screen"
    >
      <div className="mb-8 flex items-center gap-3 px-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500 shadow-lg shadow-violet-500/30">
          <BookOpen className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold gradient-text">TinyTutor</p>
          <p className="text-xs text-muted-foreground">Exam Monitor</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {links.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href}>
              <motion.span
                whileHover={{ x: 4 }}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                  active
                    ? "bg-primary/20 text-white shadow-inner"
                    : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
                )}
              >
                <Icon className={cn("h-4 w-4", active && "text-violet-400")} />
                {label}
              </motion.span>
            </Link>
          );
        })}
      </nav>

      <p className="mt-auto px-2 text-xs text-muted-foreground">Powered by Ollama · Local AI</p>
    </motion.aside>
  );
}
