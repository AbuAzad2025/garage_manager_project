# 🔒 دليل إعداد HTTPS Certificate (Let's Encrypt)

## الخطوة 1: تثبيت Certbot

### على Ubuntu/Debian:
```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
```

### على CentOS/RHEL:
```bash
sudo yum install certbot python3-certbot-nginx
```

### على Windows (غير موصى به للإنتاج):
استخدم WSL أو Docker

---

## الخطوة 2: الحصول على الشهادة

### إذا كنت تستخدم Nginx:
```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### إذا كنت تستخدم Apache:
```bash
sudo certbot --apache -d yourdomain.com -d www.yourdomain.com
```

### للحصول على الشهادة فقط (بدون تكوين تلقائي):
```bash
sudo certbot certonly --standalone -d yourdomain.com
```

---

## الخطوة 3: التجديد التلقائي

Certbot يضيف cron job تلقائياً للتجديد. للتحقق:

```bash
sudo certbot renew --dry-run
```

---

## الخطوة 4: تكوين Nginx (مثال)

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## الخطوة 5: تفعيل HTTPS في Flask

في `config.py`:
```python
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PREFERRED_URL_SCHEME = 'https'
```

---

## ✅ التحقق من النجاح

1. زيارة `https://yourdomain.com`
2. التحقق من القفل الأخضر في المتصفح
3. اختبار على: https://www.ssllabs.com/ssltest/

---

## 🔄 التجديد اليدوي (إذا لزم الأمر)

```bash
sudo certbot renew
sudo systemctl reload nginx
```

---

## 🚨 حل المشاكل الشائعة

### المشكلة: Port 80 مشغول
```bash
sudo lsof -i :80
sudo systemctl stop nginx
sudo certbot certonly --standalone -d yourdomain.com
sudo systemctl start nginx
```

### المشكلة: DNS غير محدث
انتظر 24-48 ساعة لتحديث DNS عالمياً

---

**مدة التنفيذ:** 10-15 دقيقة  
**التكلفة:** مجاني 100%  
**الصلاحية:** 90 يوم (تجديد تلقائي)

