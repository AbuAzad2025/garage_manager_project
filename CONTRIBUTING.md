<div align="center">

# 🤝 دليل المساهمة | Contributing Guide

<img src="static/img/azad_logo.png" alt="Azad Logo" width="150"/>

### **Garage Manager System**

**نرحب بمساهماتكم! 🎉**
**We welcome your contributions!**

---

</div>

## 📋 جدول المحتويات | Table of Contents

- [مقدمة](#-مقدمة--introduction)
- [كيف يمكنك المساهمة؟](#-كيف-يمكنك-المساهمة--how-can-you-contribute)
- [إعداد بيئة التطوير](#-إعداد-بيئة-التطوير--development-setup)
- [معايير الكود](#-معايير-الكود--code-standards)
- [عملية المراجعة](#-عملية-المراجعة--review-process)
- [قواعد السلوك](#-قواعد-السلوك--code-of-conduct)

---

## 👋 مقدمة | Introduction

شكراً لاهتمامك بالمساهمة في نظام إدارة الكراج! نحن نقدر جميع أنواع المساهمات، من تحسينات الكود إلى تحسينات الوثائق.

Thank you for your interest in contributing to the Garage Manager System! We appreciate all types of contributions, from code improvements to documentation enhancements.

---

## 💡 كيف يمكنك المساهمة؟ | How Can You Contribute?

### 1️⃣ 🐛 الإبلاغ عن الأخطاء | Reporting Bugs

- استخدم [قالب تقرير الأخطاء](.github/ISSUE_TEMPLATE/bug_report.md)
- ابحث أولاً للتأكد من عدم وجود تقرير مماثل
- قدم معلومات كافية لإعادة إنتاج المشكلة

### 2️⃣ ✨ طلب ميزات جديدة | Requesting Features

- استخدم [قالب طلب الميزة](.github/ISSUE_TEMPLATE/feature_request.md)
- اشرح لماذا هذه الميزة مفيدة
- قدم أمثلة لحالات الاستخدام

### 3️⃣ 👨‍💻 المساهمة في الكود | Contributing Code

- اتبع معايير الكود المذكورة أدناه
- اكتب اختبارات للميزات الجديدة
- حدّث الوثائق عند الحاجة

### 4️⃣ 📚 تحسين الوثائق | Improving Documentation

- صحح الأخطاء الإملائية واللغوية
- أضف أمثلة وشروحات
- ترجم الوثائق

### 5️⃣ 💰 الدعم المالي | Financial Support

- راجع [SUPPORT.md](SUPPORT.md) لمعرفة طرق الدعم

---

## 🔧 إعداد بيئة التطوير | Development Setup

### 1. Fork and Clone

```bash
# Fork المشروع على GitHub أولاً
# ثم استنسخه

git clone https://github.com/YOUR_USERNAME/garage_manager.git
cd garage_manager
```

### 2. إعداد البيئة الافتراضية

```bash
# أنشئ بيئة افتراضية
python -m venv venv

# فعّلها
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. تثبيت المتطلبات

```bash
# ثبت متطلبات التطوير
pip install -r requirements.txt
pip install -r requirements-dev.txt  # إن وجد
```

### 4. إعداد قاعدة البيانات

```bash
# أنشئ قاعدة بيانات للتطوير
flask db upgrade
flask seed-roles
```

### 5. تشغيل النظام

```bash
# شغّل في وضع التطوير
python app.py

# أو
flask run --debug
```

---

## 📝 معايير الكود | Code Standards

### Python Code Style

نتبع **PEP 8** مع بعض الاستثناءات:

```python
# ✅ جيد
def calculate_total(items: list) -> Decimal:
    """
    حساب المجموع الكلي للعناصر.
    Calculate the total sum of items.
    
    Args:
        items: قائمة العناصر | List of items
        
    Returns:
        المجموع الكلي | Total sum
    """
    return sum(item.price for item in items)

# ❌ سيء
def calc(i):
    return sum(x.p for x in i)
```

### معايير التسمية | Naming Conventions

```python
# Classes: PascalCase
class CustomerService:
    pass

# Functions/Methods: snake_case
def get_customer_balance():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_ITEMS_PER_PAGE = 50

# Variables: snake_case
customer_name = "أحمد"
```

### التعليقات | Comments

```python
# ✅ استخدم تعليقات ثنائية اللغة
# احسب المجموع | Calculate total
total = sum(prices)

# ✅ وثّق الدوال المعقدة
def complex_calculation(x, y, z):
    """
    دالة معقدة تحسب...
    A complex function that calculates...
    """
    pass
```

### Import Order

```python
# 1. Standard library
import os
import sys
from datetime import datetime

# 2. Third-party
from flask import Flask, render_template
from sqlalchemy import Column, Integer

# 3. Local
from models import User, Customer
from utils import format_currency
```

---

## 🔄 عملية المساهمة | Contribution Process

### 1. أنشئ Branch جديد

```bash
# للميزات الجديدة
git checkout -b feature/my-awesome-feature

# لإصلاح الأخطاء
git checkout -b fix/bug-description

# للوثائق
git checkout -b docs/documentation-improvement
```

### 2. اعمل على تغييراتك

```bash
# اكتب الكود
# ...

# اختبر التغييرات
python -m pytest  # إن وجدت اختبارات

# تأكد من عدم وجود أخطاء
flask run
```

### 3. Commit التغييرات

```bash
# استخدم رسائل commit واضحة
git add .
git commit -m "Add: feature description"

# أمثلة على رسائل commit جيدة:
# "Add: customer export to Excel"
# "Fix: calculation error in totals"
# "Update: README with new features"
# "Remove: deprecated function"
```

### 4. Push للـ Fork

```bash
git push origin feature/my-awesome-feature
```

### 5. افتح Pull Request

- اذهب إلى صفحة المشروع على GitHub
- اضغط على "New Pull Request"
- املأ [قالب PR](.github/pull_request_template.md)
- انتظر المراجعة

---

## 🔍 عملية المراجعة | Review Process

### ما نبحث عنه | What We Look For

✅ **الجودة | Quality**
- كود نظيف ومقروء
- يتبع معايير المشروع
- مختبر جيداً

✅ **الوثائق | Documentation**
- تعليقات واضحة
- تحديث README إن لزم
- أمثلة للاستخدام

✅ **الاختبارات | Tests**
- اختبارات للميزات الجديدة
- جميع الاختبارات تنجح
- لا regression في الميزات الموجودة

✅ **الأمان | Security**
- لا ثغرات واضحة
- Input validation مناسب
- اتباع أفضل الممارسات

### مدة المراجعة | Review Timeline

- **Simple Changes:** 1-3 أيام
- **Medium Changes:** 3-7 أيام
- **Complex Changes:** 1-2 أسبوع

### التعليقات والتغييرات | Feedback & Changes

- قد نطلب تغييرات قبل القبول
- تعاون معنا لتحسين PR
- لا تأخذ التعليقات بشكل شخصي، نحن نساعد الجميع

---

## 🎯 أنواع المساهمات | Types of Contributions

### 🔴 Priority High

- إصلاح أخطاء خطيرة | Critical bug fixes
- ثغرات أمنية | Security vulnerabilities
- مشاكل أداء | Performance issues

### 🟡 Priority Medium

- ميزات جديدة مطلوبة | Requested features
- تحسينات UI/UX | UI/UX improvements
- تحسين الوثائق | Documentation improvements

### 🟢 Priority Low

- تحسينات تجميلية | Cosmetic improvements
- إعادة هيكلة الكود | Code refactoring
- تحسينات طفيفة | Minor enhancements

---

## 📚 الموارد المفيدة | Useful Resources

### الوثائق | Documentation

- [README.md](README.md) - نظرة عامة
- [SECURITY.md](SECURITY.md) - سياسة الأمان
- [LICENSE](LICENSE) - الترخيص

### المجتمع | Community

- 💬 [Discord Server](https://discord.gg/azadsystems)
- 📧 Email: developers@azad-systems.com
- 🐦 Twitter: [@azadsystems](https://twitter.com/azadsystems)

### الأدوات | Tools

- [Black](https://github.com/psf/black) - Code formatter
- [Flake8](https://flake8.pycqa.org/) - Linting
- [Pytest](https://pytest.org/) - Testing
- [Pre-commit](https://pre-commit.com/) - Git hooks

---

## ⚠️ ما لا نقبله | What We Don't Accept

❌ **كود ضار أو مشبوه**  
❌ **انتهاك حقوق النشر**  
❌ **محتوى غير لائق**  
❌ **Spam أو إعلانات**  
❌ **تغييرات غير مختبرة**

---

## 📜 قواعد السلوك | Code of Conduct

يرجى قراءة [قواعد السلوك](CODE_OF_CONDUCT.md) قبل المساهمة.

نتوقع من جميع المساهمين:
- ✅ الاحترام والتقدير
- ✅ التواصل البنّاء
- ✅ التعاون الإيجابي
- ✅ القبول والتنوع

---

## 🎁 التقدير | Recognition

جميع المساهمين سيتم ذكرهم في:
- 📝 [CONTRIBUTORS.md](CONTRIBUTORS.md)
- 🎉 Release notes
- 💖 شكر علني على وسائل التواصل

---

## 💬 الأسئلة؟ | Questions?

إذا كان لديك أي أسئلة حول المساهمة:

- 📧 Email: contributors@azad-systems.com
- 💬 Discord: [انضم لسيرفرنا](https://discord.gg/azadsystems)
- 🐦 Twitter: [@azadsystems](https://twitter.com/azadsystems)

---

<div align="center">

## 🙏 شكراً لمساهمتك!

**Thank you for your contribution!**

**معاً نبني نظاماً أفضل**  
**Together we build a better system**

---

**Made with ❤️ in Palestine 🇵🇸**

**Azad Smart Systems Company**

---

[![Start Contributing](https://img.shields.io/badge/Start-Contributing-blue?style=for-the-badge&logo=github)](https://github.com/azadsystems/garage-manager)

</div>

