import type enAuth from '../en/auth';

export default {
  'login': 'Войти',
  'logging_in': 'Вход…',
  'login_failed': 'Не удалось войти',
  'username': 'Имя пользователя',
  'password': 'Пароль',
  'login_subtitle': 'Войдите в свою учётную запись',
  'register': 'Регистрация',
  'registering': 'Регистрация…',
  'register_failed': 'Не удалось зарегистрироваться',
  'register_subtitle': 'Создайте новый аккаунт',
  'have_account': 'Уже есть аккаунт? Войти',
  'need_account': 'Нет аккаунта? Зарегистрироваться',
} satisfies Record<keyof typeof enAuth, string> & Record<string, string>;
