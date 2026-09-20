/**
 * apiErrors — 错误翻译层文案(zh)。
 * 供 lib/api/errors.ts 的 apiErrorMessage() 使用;页面兜底文案仍在各自命名空间。
 */
export default {
  cancel: "取消",
  network: "网络连接失败,请检查网络后重试",
  auth: "登录已过期,请重新登录",
  forbidden: "没有执行此操作的权限,请联系管理员或合伙人开通",
  notFound: "数据不存在或已被删除",
  conflict: "操作与当前状态冲突,请刷新后重试",
  validation: "提交内容有误,请检查填写后重试",
  server: "服务暂时不可用,请稍后重试",
  unknown: "操作失败,请重试",
  invalidTransition: "状态流转不合法,请刷新后按流程操作",
  insufficient: "数据不足或余额不足,无法完成操作",
};
