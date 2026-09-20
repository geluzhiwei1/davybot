import { Languages } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTranslation } from "react-i18next";
import { setLanguage } from "@/lib/i18n";

const languages = [
  { code: "zh", label: "中文", fullWidth: "简体中文" },
  { code: "en", label: "EN", fullWidth: "English" },
];

export function LanguageSelector() {
  const { i18n } = useTranslation();
  const currentLang = languages.find((l) => l.code === i18n.language) ?? languages[0];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Languages className="h-4 w-4" />
          <span className="sr-only">{currentLang.fullWidth}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {languages.map((lang) => (
          <DropdownMenuItem
            key={lang.code}
            onClick={() => setLanguage(lang.code)}
            className={i18n.language === lang.code ? "bg-accent" : ""}
          >
            {lang.fullWidth}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
