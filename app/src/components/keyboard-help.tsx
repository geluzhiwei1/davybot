import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ShortcutGroup {
  categoryKey: string;
  shortcuts: { keys: string[]; descriptionKey: string }[];
}

const shortcutGroups: ShortcutGroup[] = [
  {
    categoryKey: "keyboard.group.general",
    shortcuts: [
      { keys: ["Ctrl", "/"], descriptionKey: "keyboard.helpDialog" },
      { keys: ["Ctrl", "K"], descriptionKey: "keyboard.commandPalette" },
      { keys: ["Ctrl", "S"], descriptionKey: "keyboard.save" },
      { keys: ["Ctrl", ","], descriptionKey: "keyboard.settings" },
      { keys: ["Ctrl", "Q"], descriptionKey: "keyboard.quit" },
    ],
  },
  {
    categoryKey: "keyboard.group.editor",
    shortcuts: [
      { keys: ["Ctrl", "Z"], descriptionKey: "keyboard.undo" },
      { keys: ["Ctrl", "Shift", "Z"], descriptionKey: "keyboard.redo" },
      { keys: ["Ctrl", "F"], descriptionKey: "keyboard.find" },
      { keys: ["Ctrl", "H"], descriptionKey: "keyboard.replace" },
      { keys: ["Ctrl", "G"], descriptionKey: "keyboard.gotoLine" },
      { keys: ["Tab"], descriptionKey: "keyboard.indent" },
      { keys: ["Shift", "Tab"], descriptionKey: "keyboard.unindent" },
    ],
  },
  {
    categoryKey: "keyboard.group.navigation",
    shortcuts: [
      { keys: ["Ctrl", "1-9"], descriptionKey: "keyboard.switchSidebarTab" },
      { keys: ["Ctrl", "B"], descriptionKey: "keyboard.toggleSidebar" },
      { keys: ["Ctrl", "`"], descriptionKey: "keyboard.toggleTerminal" },
      { keys: ["Ctrl", "P"], descriptionKey: "keyboard.quickOpen" },
      { keys: ["Alt", "←"], descriptionKey: "keyboard.back" },
      { keys: ["Alt", "→"], descriptionKey: "keyboard.forward" },
    ],
  },
  {
    categoryKey: "keyboard.group.chat",
    shortcuts: [
      { keys: ["Enter"], descriptionKey: "keyboard.send" },
      { keys: ["Shift", "Enter"], descriptionKey: "keyboard.newline" },
      { keys: ["Ctrl", "N"], descriptionKey: "keyboard.newChat" },
      { keys: ["Ctrl", "Shift", "C"], descriptionKey: "keyboard.clearChat" },
      { keys: ["↑"], descriptionKey: "keyboard.prevMessage" },
      { keys: ["↓"], descriptionKey: "keyboard.nextMessage" },
    ],
  },
];

interface KeyboardHelpProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardHelp({ open, onOpenChange }: KeyboardHelpProps) {
  const { t } = useTranslation("commonUi");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("keyboard.title")}</DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh]">
          <div className="space-y-6">
            {shortcutGroups.map((group) => (
              <div key={group.categoryKey}>
                <h3 className="mb-3 text-sm font-semibold text-foreground">
                  {t(group.categoryKey)}
                </h3>
                <div className="space-y-2">
                  {group.shortcuts.map((shortcut, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-muted/50"
                    >
                      <span className="text-sm text-muted-foreground">
                        {t(shortcut.descriptionKey)}
                      </span>
                      <div className="flex items-center gap-1">
                        {shortcut.keys.map((key, ki) => (
                          <span key={ki} className="flex items-center gap-1">
                            {ki > 0 && <span className="text-xs text-muted-foreground">+</span>}
                            <kbd className="inline-flex h-6 min-w-6 items-center justify-center rounded border bg-muted px-1.5 font-mono text-xs">
                              {key}
                            </kbd>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            {t("common.close")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
