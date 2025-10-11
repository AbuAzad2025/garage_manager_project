---
name: 🔒 تقرير أمني | Security Report
about: أبلغ عن ثغرة أمنية (استخدم البريد الإلكتروني للثغرات الخطيرة!) | Report a security vulnerability (use email for critical ones!)
title: '[SECURITY] '
labels: 'security'
assignees: ''
---

# ⚠️ تنبيه هام | Important Notice

<div align="center">

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║  🔒  للثغرات الأمنية الخطيرة، الرجاء عدم الإفصاح هنا!    ║
║     For critical vulnerabilities, DO NOT disclose here!     ║
║                                                              ║
║  📧  أرسل تقريراً خاصاً إلى:                               ║
║     Send a private report to:                               ║
║     security@azad-systems.com                               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

</div>

**هذا القالب للثغرات الأمنية البسيطة فقط (مثل missing security headers)**

**This template is for minor security issues only (like missing security headers)**

---

# 🔒 تقرير أمني | Security Report

## 📋 نوع الثغرة | Vulnerability Type

<!-- حدد نوع الثغرة الأمنية -->
<!-- Specify the type of security vulnerability -->

- [ ] XSS (Cross-Site Scripting)
- [ ] CSRF (Cross-Site Request Forgery)
- [ ] SQL Injection
- [ ] Authentication Bypass
- [ ] Authorization Issue
- [ ] Information Disclosure
- [ ] Insecure Configuration
- [ ] Missing Security Headers
- [ ] Weak Cryptography
- [ ] Other: 

## 🎯 مستوى الخطورة | Severity Level

<!-- حدد مستوى خطورة الثغرة بصدق -->
<!-- Honestly specify the severity level -->

- [ ] 🔴 Critical (استخدم البريد الإلكتروني! | Use email!)
- [ ] 🟠 High (استخدم البريد الإلكتروني! | Use email!)
- [ ] 🟡 Medium (يمكن استخدام GitHub | Can use GitHub)
- [ ] 🟢 Low (مناسب لـ GitHub | Suitable for GitHub)

> ⚠️ **إذا اخترت Critical أو High، يرجى حذف هذا Issue واستخدام البريد الإلكتروني!**

## 📝 وصف الثغرة | Vulnerability Description

<!-- صف الثغرة بالتفصيل -->
<!-- Describe the vulnerability in detail -->

**ما هي الثغرة؟ | What is the vulnerability?**


**أين تقع الثغرة؟ | Where is the vulnerability located?**

- المسار | Path: 
- الملف | File: 
- السطر | Line: 
- الوظيفة | Function: 

## 🔄 خطوات إعادة الإنتاج | Steps to Reproduce

<!-- صف بالتفصيل كيفية استغلال الثغرة -->
<!-- Describe in detail how to exploit the vulnerability -->

1. 
2. 
3. 
4. 

## 💥 التأثير المحتمل | Potential Impact

<!-- ما الذي يمكن أن يحدث بسبب هذه الثغرة؟ -->
<!-- What could happen because of this vulnerability? -->

**ما الذي يمكن للمهاجم فعله؟ | What can an attacker do?**
- 
- 
- 

**ما البيانات المعرضة للخطر؟ | What data is at risk?**
- 
- 
- 

**من يتأثر؟ | Who is affected?**
- [ ] جميع المستخدمين | All users
- [ ] المستخدمين المسجلين | Authenticated users
- [ ] المسؤولين فقط | Administrators only
- [ ] ظروف خاصة | Special conditions

## 💻 البيئة | Environment

**إصدار النظام | System Version:**
- Version: 

**Python Version:**
- Version: 

**قاعدة البيانات | Database:**
- Type: 
- Version: 

**المتصفح (إن وجد) | Browser (if applicable):**
- Browser: 
- Version: 

## 🔬 إثبات المفهوم | Proof of Concept

<!-- قدم مثالاً عملياً (غير ضار) لاستغلال الثغرة -->
<!-- Provide a practical (harmless) example of exploiting the vulnerability -->

```python
# مثال للكود
# Code example


```

## 🛡️ الحل المقترح | Proposed Solution

<!-- كيف يمكن إصلاح هذه الثغرة؟ -->
<!-- How can this vulnerability be fixed? -->

**الإصلاح الموصى به | Recommended Fix:**


**بدائل | Alternatives:**


## 📚 المراجع | References

<!-- روابط لمعلومات إضافية عن هذا النوع من الثغرات -->
<!-- Links to additional information about this type of vulnerability -->

- OWASP: 
- CVE: 
- CWE: 
- Other: 

## 🤝 الإفصاح المسؤول | Responsible Disclosure

<!-- هل أنت ملتزم بسياسة الإفصاح المسؤول؟ -->
<!-- Are you committed to responsible disclosure policy? -->

- [ ] نعم، لن أفصح علناً حتى يتم الإصلاح
- [ ] نعم، سأعطي 90 يوم للإصلاح قبل الإفصاح
- [ ] نعم، سأتعاون مع فريق الأمان
- [ ] فهمت سياسة الإفصاح المسؤول

## 💰 مكافأة الأمان | Bug Bounty

<!-- هل تريد المشاركة في برنامج مكافآت الأمان؟ -->
<!-- Do you want to participate in the bug bounty program? -->

- [ ] نعم، أريد التقدم للحصول على مكافأة | Yes, I want to apply for a reward
- [ ] لا، هذا تطوع | No, this is voluntary

**معلومات الاتصال (اختيارية) | Contact Information (Optional):**
- Name: 
- Email: 
- GitHub: 
- PayPal: (للمكافأة | for reward)

## ✅ قائمة التحقق | Checklist

<!-- تأكد من إتمام هذه النقاط قبل إرسال التقرير -->
<!-- Ensure these points are completed before submitting -->

- [ ] حددت مستوى الخطورة بدقة
- [ ] قدمت خطوات واضحة لإعادة الإنتاج
- [ ] وصفت التأثير المحتمل بالتفصيل
- [ ] اقترحت حلاً إن أمكن
- [ ] التزمت بسياسة الإفصاح المسؤول
- [ ] لم أستغل الثغرة بشكل ضار
- [ ] أكدت أن هذه ثغرة بسيطة ومناسبة لـ GitHub

## 📎 معلومات إضافية | Additional Information

<!-- أي معلومات أخرى قد تكون مفيدة -->
<!-- Any other information that might be helpful -->



---

<div align="center">

## 🙏 شكراً لمساعدتنا في تأمين النظام

**Thank you for helping us secure the system**

**الأمان مسؤولية مشتركة**
**Security is a shared responsibility**

---

### 📞 للاتصال السري | For Confidential Contact

**📧 Email:** security@azad-systems.com  
**🔑 PGP Key:** Available upon request

**وقت الاستجابة | Response Time:** 24-48 hours

---

**📖 اقرأ سياسة الأمان الكاملة:** [SECURITY.md](../../SECURITY.md)

**💰 اقرأ عن برنامج المكافآت:** [Bug Bounty Program](../../SECURITY.md#-مكافآت-الأمان--bug-bounty-program)

</div>

