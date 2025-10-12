#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اختبار شامل لـ API الشيكات
"""

from app import app

with app.test_client() as client:
    with app.app_context():
        print("\n" + "="*80)
        print("🧪 اختبار API الشيكات الشامل")
        print("="*80)
        
        # 1. GET /checks/api/checks - جميع الشيكات
        print("\n1️⃣ GET /checks/api/checks (جميع الشيكات)")
        print("-" * 80)
        resp = client.get('/checks/api/checks')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"   ✅ Status: {resp.status_code}")
            print(f"   📊 عدد الشيكات: {data.get('total', 0)}")
            print(f"   🔍 Success: {data.get('success')}")
            
            # عرض أول 5 شيكات
            checks = data.get('checks', [])
            print(f"\n   📋 أول 5 شيكات:")
            for i, check in enumerate(checks[:5], 1):
                print(f"      {i}. {check.get('check_number')} - {check.get('check_bank')}")
                print(f"         المبلغ: {check.get('amount')} {check.get('currency')}")
                print(f"         النوع: {check.get('source')} | الاتجاه: {check.get('direction')}")
                print(f"         الحالة: {check.get('status_ar')} | الاستحقاق: {check.get('due_date_formatted')}")
        else:
            print(f"   ❌ خطأ: {resp.status_code}")
            print(f"   {resp.get_json()}")
        
        # 2. GET /checks/api/checks?direction=in - الشيكات الواردة فقط
        print("\n\n2️⃣ GET /checks/api/checks?direction=in (الواردة)")
        print("-" * 80)
        resp = client.get('/checks/api/checks?direction=in')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"   ✅ عدد الشيكات الواردة: {data.get('total', 0)}")
        
        # 3. GET /checks/api/checks?direction=out - الشيكات الصادرة فقط
        print("\n3️⃣ GET /checks/api/checks?direction=out (الصادرة)")
        print("-" * 80)
        resp = client.get('/checks/api/checks?direction=out')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"   ✅ عدد الشيكات الصادرة: {data.get('total', 0)}")
        
        # 4. GET /checks/api/checks?status=pending - المعلقة فقط
        print("\n4️⃣ GET /checks/api/checks?status=pending (المعلقة)")
        print("-" * 80)
        resp = client.get('/checks/api/checks?status=pending')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"   ✅ عدد الشيكات المعلقة: {data.get('total', 0)}")
        
        # 5. GET /checks/api/checks?status=overdue - المتأخرة
        print("\n5️⃣ GET /checks/api/checks?status=overdue (المتأخرة)")
        print("-" * 80)
        resp = client.get('/checks/api/checks?status=overdue')
        if resp.status_code == 200:
            data = resp.get_json()
            print(f"   ⚠️ عدد الشيكات المتأخرة: {data.get('total', 0)}")
            if data.get('total', 0) > 0:
                for check in data.get('checks', [])[:3]:
                    print(f"      - {check.get('check_number')}: متأخر {abs(check.get('days_until_due', 0))} يوم")
        
        # 6. GET /checks/api/statistics - الإحصائيات
        print("\n\n6️⃣ GET /checks/api/statistics")
        print("-" * 80)
        resp = client.get('/checks/api/statistics')
        if resp.status_code == 200:
            data = resp.get_json()
            stats = data.get('statistics', {})
            
            incoming = stats.get('incoming', {})
            print(f"   📥 الشيكات الواردة:")
            print(f"      • إجمالي المبلغ: {incoming.get('total_amount', 0):.2f}")
            print(f"      • عدد المتأخرة: {incoming.get('overdue_count', 0)}")
            print(f"      • المستحقة هذا الأسبوع: {incoming.get('this_week_count', 0)}")
            
            outgoing = stats.get('outgoing', {})
            print(f"\n   📤 الشيكات الصادرة:")
            print(f"      • إجمالي المبلغ: {outgoing.get('total_amount', 0):.2f}")
            print(f"      • عدد المتأخرة: {outgoing.get('overdue_count', 0)}")
            print(f"      • المستحقة هذا الأسبوع: {outgoing.get('this_week_count', 0)}")
        
        # 7. GET /checks/api/alerts - التنبيهات
        print("\n\n7️⃣ GET /checks/api/alerts")
        print("-" * 80)
        resp = client.get('/checks/api/alerts')
        if resp.status_code == 200:
            data = resp.get_json()
            alerts = data.get('alerts', [])
            print(f"   ⚠️ عدد التنبيهات: {data.get('count', 0)}")
            
            if len(alerts) > 0:
                print(f"\n   🔔 أهم التنبيهات:")
                for alert in alerts[:5]:
                    severity = alert.get('severity')
                    emoji = '🔴' if severity == 'danger' else '🟡' if severity == 'warning' else '🔵'
                    print(f"      {emoji} {alert.get('title')}")
                    print(f"         {alert.get('message')}")
        
        # 8. اختبار المصادر المختلفة
        print("\n\n8️⃣ تحليل المصادر")
        print("-" * 80)
        resp = client.get('/checks/api/checks')
        if resp.status_code == 200:
            data = resp.get_json()
            checks = data.get('checks', [])
            
            sources = {}
            for check in checks:
                source = check.get('source', 'Unknown')
                sources[source] = sources.get(source, 0) + 1
            
            print("   📊 توزيع الشيكات حسب المصدر:")
            for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
                print(f"      • {source}: {count} شيك")
        
        print("\n" + "="*80)
        print("✅ اكتمل اختبار API بنجاح")
        print("="*80 + "\n")

