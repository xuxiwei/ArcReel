import type enAuth from "@/i18n/en/auth";

export default {
  'login': 'Đăng nhập',
  'logging_in': 'Đang đăng nhập...',
  'login_failed': 'Đăng nhập thất bại',
  'username': 'Tên đăng nhập',
  'password': 'Mật khẩu',
  'login_subtitle': 'Đăng nhập bằng tài khoản của bạn',
  'register': 'Đăng ký',
  'registering': 'Đang đăng ký...',
  'register_failed': 'Đăng ký thất bại',
  'register_subtitle': 'Tạo tài khoản mới',
  'have_account': 'Đã có tài khoản? Đăng nhập',
  'need_account': 'Chưa có tài khoản? Đăng ký',
  'invite_code': 'Mã mời',
  'invite_code_hint': 'Chỉ cần khi đăng ký theo lời mời',
  'register_closed': 'Hiện chưa mở đăng ký',
  'invite_invalid': 'Mã mời bị thiếu, không hợp lệ, đã dùng hết hoặc đã hết hạn',
} satisfies Record<keyof typeof enAuth, string>;
