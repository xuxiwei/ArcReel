import type enAuth from '../en/auth';

export default {
  'login': '登录',
  'logging_in': '登录中…',
  'login_failed': '登录失败',
  'username': '用户名',
  'password': '密码',
  'login_subtitle': '使用账号登录',
  'register': '注册',
  'registering': '注册中…',
  'register_failed': '注册失败',
  'register_subtitle': '创建新账号',
  'have_account': '已有账号？去登录',
  'need_account': '没有账号？去注册',
} satisfies Record<keyof typeof enAuth, string>;
