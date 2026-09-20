import { useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "@/hooks/use-mobile";

export interface ShortcutDefinition {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean;
  description: string;
  action: () => void;
  /** Only trigger when NOT focused on an input/textarea */
  global?: boolean;
}

interface UseKeyboardShortcutsOptions {
  shortcuts: ShortcutDefinition[];
  enabled?: boolean;
}

export function useKeyboardShortcuts({ shortcuts, enabled = true }: UseKeyboardShortcutsOptions) {
  // 移动端无实体键盘 — 不注册全局快捷键(避免外接/虚拟键盘误触)。
  const isMobile = useIsMobile();
  const shortcutsRef = useRef(shortcuts);
  shortcutsRef.current = shortcuts;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;

      // Ignore when typing in input/textarea/contenteditable unless global
      const target = e.target as HTMLElement;
      const isInputFocused =
        target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;

      for (const shortcut of shortcutsRef.current) {
        if (shortcut.global && isInputFocused) continue;

        const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase();
        const ctrlMatch = shortcut.ctrl ? e.ctrlKey || e.metaKey : !(e.ctrlKey || e.metaKey);
        const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey;
        const altMatch = shortcut.alt ? e.altKey : !e.altKey;

        if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
          e.preventDefault();
          shortcut.action();
          return;
        }
      }
    },
    [enabled],
  );

  useEffect(() => {
    if (!enabled || isMobile) return;
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown, enabled, isMobile]);
}

/**
 * Default global shortcuts for the app.
 */
export function useGlobalShortcuts(options: {
  onToggleSidebar?: () => void;
  onCommandPalette?: () => void;
  onNewChat?: () => void;
  onSettings?: () => void;
  onKeyboardHelp?: () => void;
  enabled?: boolean;
}) {
  const { t } = useTranslation("hooksUi");
  const shortcuts: ShortcutDefinition[] = [
    {
      key: "b",
      ctrl: true,
      description: t("shortcuts.toggleSidebar"),
      action: () => options.onToggleSidebar?.(),
      global: true,
    },
    {
      key: "k",
      ctrl: true,
      description: t("shortcuts.commandPalette"),
      action: () => options.onCommandPalette?.(),
    },
    {
      key: "n",
      ctrl: true,
      description: t("shortcuts.newChat"),
      action: () => options.onNewChat?.(),
      global: true,
    },
    {
      key: ",",
      ctrl: true,
      description: t("shortcuts.openSettings"),
      action: () => options.onSettings?.(),
      global: true,
    },
    {
      key: "/",
      ctrl: true,
      description: t("shortcuts.keyboardHelp"),
      action: () => options.onKeyboardHelp?.(),
    },
  ];

  useKeyboardShortcuts({ shortcuts, enabled: options.enabled });
}
