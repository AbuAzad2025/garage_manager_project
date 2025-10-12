#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
مراقبة لحظية لوحدة الشيكات
Real-time Checks Module Monitor
"""

import requests
import time
import os
from datetime import datetime

def clear_screen():
    """مسح الشاشة"""
    os.system('cls' if os.name == 'nt' else 'clear')

def monitor_checks():
    """مراقبة مستمرة للشيكات"""
    
    while True:
        clear_screen()
        
        print("="*80)
        print(f"🔍 مراقبة وحدة الشيكات - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        try:
            # 1. فحص السيرفر
            resp = requests.get('http://localhost:5000/health', timeout=2)
            if resp.status_code == 200:
                print("\n✅ السيرفر يعمل: http://localhost:5000")
            else:
                print(f"\n⚠️ السيرفر Status: {resp.status_code}")
        except Exception as e:
            print(f"\n❌ السيرفر متوقف: {str(e)}")
            print("\n⏸️  في انتظار السيرفر...")
            time.sleep(5)
            continue
        
        # 2. جلب إحصائيات الشيكات
        try:
            resp = requests.get('http://localhost:5000/checks/api/statistics', timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                stats = data.get('statistics', {})
                
                incoming = stats.get('incoming', {})
                outgoing = stats.get('outgoing', {})
                
                print("\n📊 الإحصائيات:")
                print("-" * 80)
                print(f"   📥 شيكات واردة:")
                print(f"      • الإجمالي: {incoming.get('total_amount', 0):,.2f} ₪")
                print(f"      • متأخرة: {incoming.get('overdue_count', 0)} شيك")
                print(f"      • هذا الأسبوع: {incoming.get('this_week_count', 0)} شيك")
                
                print(f"\n   📤 شيكات صادرة:")
                print(f"      • الإجمالي: {outgoing.get('total_amount', 0):,.2f} ₪")
                print(f"      • متأخرة: {outgoing.get('overdue_count', 0)} شيك")
                print(f"      • هذا الأسبوع: {outgoing.get('this_week_count', 0)} شيك")
                
        except Exception as e:
            print(f"\n⚠️ لم يتم جلب الإحصائيات: {str(e)}")
        
        # 3. جلب التنبيهات
        try:
            resp = requests.get('http://localhost:5000/checks/api/alerts', timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                alerts = data.get('alerts', [])
                
                if len(alerts) > 0:
                    print(f"\n⚠️ التنبيهات ({len(alerts)}):")
                    print("-" * 80)
                    for i, alert in enumerate(alerts[:5], 1):
                        severity_emoji = {
                            'danger': '🔴',
                            'warning': '🟡',
                            'info': '🔵'
                        }.get(alert.get('severity'), '⚪')
                        
                        print(f"   {severity_emoji} {i}. {alert.get('title')}")
                        print(f"      {alert.get('message')}")
                        print(f"      المبلغ: {alert.get('amount'):,.2f} {alert.get('currency')}")
                        print()
                else:
                    print(f"\n✅ لا توجد تنبيهات - كل شيء على ما يرام!")
                    
        except Exception as e:
            print(f"\n⚠️ لم يتم جلب التنبيهات: {str(e)}")
        
        # 4. عرض آخر الشيكات
        try:
            resp = requests.get('http://localhost:5000/checks/api/checks', timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                checks = data.get('checks', [])
                
                print(f"\n📋 آخر الشيكات (إجمالي: {len(checks)}):")
                print("-" * 80)
                
                # تصنيف حسب الحالة
                categorized = {
                    'PENDING': [],
                    'OVERDUE': [],
                    'CASHED': [],
                    'RETURNED': [],
                    'BOUNCED': []
                }
                
                for check in checks:
                    status = check.get('status', '').upper()
                    if status in categorized:
                        categorized[status].append(check)
                    elif status == 'DUE_SOON':
                        categorized['PENDING'].append(check)
                
                print(f"   ⏳ آجلة (PENDING):    {len(categorized['PENDING'])} شيك")
                print(f"   ⚠️ متأخرة (OVERDUE):   {len(categorized['OVERDUE'])} شيك")
                print(f"   ✅ مسحوبة (CASHED):   {len(categorized['CASHED'])} شيك")
                print(f"   🔄 مرتجعة (RETURNED): {len(categorized['RETURNED'])} شيك")
                print(f"   ❌ مرفوضة (BOUNCED):  {len(categorized['BOUNCED'])} شيك")
                
                # عرض عينة من الشيكات المتأخرة
                if categorized['OVERDUE']:
                    print(f"\n   🚨 شيكات متأخرة تحتاج متابعة:")
                    for check in categorized['OVERDUE'][:3]:
                        days = abs(check.get('days_until_due', 0))
                        print(f"      • {check.get('check_number')}: متأخر {days} يوم - {check.get('amount'):,.0f} {check.get('currency')}")
                
        except Exception as e:
            print(f"\n⚠️ لم يتم جلب الشيكات: {str(e)}")
        
        # معلومات الوصول
        print("\n" + "="*80)
        print("🌐 نقاط الوصول:")
        print("   • الصفحة الرئيسية:  http://localhost:5000")
        print("   • وحدة الشيكات:     http://localhost:5000/checks/")
        print("   • إضافة شيك:        http://localhost:5000/checks/new")
        print("   • التقارير:         http://localhost:5000/checks/reports")
        print("="*80)
        
        print("\n💡 اضغط Ctrl+C للخروج | التحديث التالي بعد 10 ثواني...")
        
        # انتظار قبل التحديث التالي
        time.sleep(10)

if __name__ == "__main__":
    print("\n🚀 بدء المراقبة اللحظية...\n")
    try:
        monitor_checks()
    except KeyboardInterrupt:
        print("\n\n✋ تم إيقاف المراقبة")
        print("="*80)

