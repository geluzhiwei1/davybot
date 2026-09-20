import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Keyboard } from "lucide-react";
import { useTranslation } from "react-i18next";

/** category/name 走 i18n key（userUi ns） */
const SHORTCUTS = [
  {
    category: "shortcuts.cat.general",
    items: [
      { name: "shortcuts.item.newChat", keys: "Ctrl+N" },
      { name: "shortcuts.item.search", keys: "Ctrl+K" },
      { name: "shortcuts.item.settings", keys: "Ctrl+," },
      { name: "shortcuts.item.commandPalette", keys: "Ctrl+Shift+P" },
    ],
  },
  {
    category: "shortcuts.cat.editor",
    items: [
      { name: "shortcuts.item.saveFile", keys: "Ctrl+S" },
      { name: "shortcuts.item.closeTab", keys: "Ctrl+W" },
      { name: "shortcuts.item.format", keys: "Shift+Alt+F" },
    ],
  },
  {
    category: "shortcuts.cat.nav",
    items: [
      { name: "shortcuts.item.toggleSidebar", keys: "Ctrl+B" },
      { name: "shortcuts.item.toggleTerminal", keys: "Ctrl+`" },
      { name: "shortcuts.item.nextTab", keys: "Ctrl+Tab" },
    ],
  },
];

export function ShortcutsTab() {
  const { t } = useTranslation("userUi");
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Keyboard className="h-4 w-4" /> {t("shortcuts.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {SHORTCUTS.map((group) => (
            <div key={group.category}>
              <p className="text-xs font-medium text-muted-foreground mb-2">{t(group.category)}</p>
              <div className="space-y-1.5">
                {group.items.map((item) => (
                  <div key={item.name} className="flex items-center justify-between py-1">
                    <span className="text-sm">{t(item.name)}</span>
                    <Badge variant="outline" className="text-[11px] font-mono h-6 px-2">
                      {item.keys}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
