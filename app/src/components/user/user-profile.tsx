import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { User, Mail, Phone, Crown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useState } from "react";

const DEMO_PROFILE = {
  id: "u1",
  nickname: "法律顾问",
  email: "legal@example.com",
  phone: "138****8888",
  avatar: undefined,
  plan: "专业版",
  tokenQuota: 1000000,
  tokenUsed: 356789,
  createdAt: "2024-01-15",
  preferences: {
    language: "zh",
    timezone: "Asia/Shanghai",
    theme: "dark" as const,
    fontSize: 14,
    autoSave: true,
    compactMode: false,
  },
};

export function UserProfileTab() {
  const { t } = useTranslation("userUi");
  const [profile] = useState(DEMO_PROFILE);
  const tokenPercent = Math.round((profile.tokenUsed / profile.tokenQuota) * 100);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">{t("profile.personalInfo")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center">
              <User className="h-8 w-8 text-muted-foreground" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{profile.nickname}</span>
                <Badge variant="outline" className="text-[10px] gap-1">
                  <Crown className="h-3 w-3" /> {profile.plan}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-1">ID: {profile.id}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">{t("profile.nickname")}</label>
              <Input value={profile.nickname} className="mt-1 h-8 text-sm" readOnly />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t("profile.email")}</label>
              <div className="flex items-center gap-1 mt-1 text-sm">
                <Mail className="h-3.5 w-3.5 text-muted-foreground" />{" "}
                {profile.email || t("profile.notSet")}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">{t("profile.phone")}</label>
              <div className="flex items-center gap-1 mt-1 text-sm">
                <Phone className="h-3.5 w-3.5 text-muted-foreground" />{" "}
                {profile.phone || t("profile.notBound")}
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">{t("profile.registeredAt")}</label>
              <div className="mt-1 text-sm">{profile.createdAt}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">{t("profile.tokenUsage")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>
                {t("profile.used", {
                  used: `${(profile.tokenUsed / 1000).toFixed(1)}K`,
                  quota: `${(profile.tokenQuota / 1000).toFixed(0)}K`,
                })}
              </span>
              <span className="text-muted-foreground">{tokenPercent}%</span>
            </div>
            <Progress value={tokenPercent} className="h-2" />
            <Button variant="outline" size="sm" className="w-full h-7 text-xs">
              {t("profile.upgrade")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
