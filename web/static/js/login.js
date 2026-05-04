Vue.createApp({
    delimiters: ['[[', ']]'],
    data() {
        return {
            loading: false,
            error: '',
            form: {username: '', password: '', remember: false}
        };
    },
    methods: {
        async submit() {
            this.loading = true;
            this.error = '';
            const body = new FormData();
            body.append('username', this.form.username);
            body.append('password', this.form.password);
            if (this.form.remember) body.append('remember', 'on');

            try {
                const response = await fetch('/login', {method: 'POST', body});
                if (response.ok) {
                    location.href = '/';
                    return;
                }
                const data = await response.json().catch(() => ({}));
                this.error = data.detail || '登录失败，请重试';
            } catch {
                this.error = '网络错误，请检查连接';
            } finally {
                this.loading = false;
            }
        }
    }
}).mount('#login-app');
