import * as React from "react";

const MOBILE_BREAKPOINT = 768;

export function useIsMobile() {
  // 方案 Phase 3.6:懒初始化首帧即得真实视口(纯客户端 SPA,无 SSR 水合顾虑)。
  // 原先 undefined → effect 后置位,移动端首帧恒 false,壳层/降级页会闪桌面态。
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(
    () => typeof window !== "undefined" && window.innerWidth < MOBILE_BREAKPOINT,
  );

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
    const onChange = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    };
    mql.addEventListener("change", onChange);
    setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return !!isMobile;
}
