# ai_self_review.py - AI Self-Review System
# Location: /garage_manager/services/ai_self_review.py
# Description: AI self-review and learning system

"""
AI Self-Review System - نظام المراجعة الذاتية
المساعد يراجع نفسه ويتعلم من أخطائه
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path


INTERACTIONS_LOG = 'instance/ai_interactions.json'
SELF_AUDIT_LOG = 'instance/ai_self_audit.json'
TRAINING_POLICY = 'instance/ai_training_policy.json'


def log_interaction(question, answer, confidence, search_results):
    """تسجيل كل تفاعل مع المساعد"""
    try:
        os.makedirs('instance', exist_ok=True)
        
        interactions = []
        if os.path.exists(INTERACTIONS_LOG):
            with open(INTERACTIONS_LOG, 'r', encoding='utf-8') as f:
                interactions = json.load(f)
        
        interactions.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'question': question[:200],
            'answer': answer[:300],
            'confidence': confidence,
            'data_keys': list(search_results.keys()) if search_results else [],
            'has_data': len(search_results) > 1 if search_results else False
        })
        
        interactions = interactions[-100:]
        
        with open(INTERACTIONS_LOG, 'w', encoding='utf-8') as f:
            json.dump(interactions, f, ensure_ascii=False, indent=2)
        
    except Exception as e:
        print(f"⚠️ فشل تسجيل التفاعل: {str(e)}")


def analyze_recent_interactions(count=100):
    """تحليل آخر N تفاعل - اكتشاف نقاط الضعف"""
    try:
        if not os.path.exists(INTERACTIONS_LOG):
            return {
                'total': 0,
                'analyzed': 0,
                'avg_confidence': 0,
                'weak_areas': []
            }
        
        with open(INTERACTIONS_LOG, 'r', encoding='utf-8') as f:
            interactions = json.load(f)
        
        if not interactions:
            return {'total': 0, 'analyzed': 0}
        
        recent = interactions[-count:]
        
        total_confidence = sum(i.get('confidence', 0) for i in recent)
        avg_confidence = total_confidence / len(recent) if recent else 0
        
        weak_interactions = [i for i in recent if i.get('confidence', 0) < 70]
        
        weak_areas = []
        for interaction in weak_interactions:
            question_keywords = interaction['question'].lower()
            if 'نفق' in question_keywords or 'مصروف' in question_keywords:
                weak_areas.append('expenses')
            elif 'فاتورة' in question_keywords:
                weak_areas.append('invoices')
            elif 'صيانة' in question_keywords:
                weak_areas.append('services')
        
        unique_weak_areas = list(set(weak_areas))
        
        return {
            'total': len(interactions),
            'analyzed': len(recent),
            'avg_confidence': round(avg_confidence, 2),
            'weak_count': len(weak_interactions),
            'weak_areas': unique_weak_areas,
            'quality_score': 'ممتاز' if avg_confidence >= 90 else 'جيد' if avg_confidence >= 70 else 'يحتاج تحسين'
        }
    
    except Exception as e:
        return {'error': str(e)}


def generate_self_audit_report():
    """توليد تقرير المراجعة الذاتية"""
    try:
        analysis = analyze_recent_interactions(100)
        
        policy = load_training_policy()
        
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'policy_version': policy.get('policy_version', 'N/A'),
            'interactions_analysis': analysis,
            'system_health': 'healthy',
            'recommendations': []
        }
        
        if analysis.get('avg_confidence', 0) < 70:
            report['system_health'] = 'needs_improvement'
            report['recommendations'].append('تحسين جودة البيانات المرسلة للـ AI')
        
        if analysis.get('weak_areas'):
            for area in analysis['weak_areas']:
                report['recommendations'].append(f'تحسين البحث في: {area}')
        
        if not analysis.get('weak_areas') and analysis.get('avg_confidence', 0) >= 90:
            report['system_health'] = 'excellent'
            report['recommendations'].append('✅ الأداء ممتاز - استمر!')
        
        os.makedirs('instance', exist_ok=True)
        with open(SELF_AUDIT_LOG, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return report
        
    except Exception as e:
        return {'error': str(e)}


def load_training_policy():
    """تحميل سياسة التدريب"""
    try:
        if os.path.exists(TRAINING_POLICY):
            with open(TRAINING_POLICY, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except:
        return {}


def check_policy_compliance(confidence, has_data):
    """التحقق من الالتزام بالسياسة - محسّن للإجابات الجزئية"""
    policy = load_training_policy()
    
    min_confidence = policy.get('core_rules', {}).get('confidence_threshold', {}).get('minimum', 20)
    
    compliance = {
        'passed': True,
        'violations': [],
        'allow_partial': False
    }
    
    # السماح بإجابات جزئية إذا كانت الثقة بين 20-50%
    if 20 <= confidence < 50:
        compliance['allow_partial'] = True
        compliance['passed'] = True
    elif confidence < min_confidence:
        compliance['passed'] = False
        compliance['violations'].append(f'Confidence {confidence}% < الحد الأدنى {min_confidence}%')
    
    # تخفيف قاعدة "لا تخمين"
    if not has_data and confidence < 15 and policy.get('core_rules', {}).get('no_guessing', {}).get('enabled'):
        compliance['passed'] = False
        compliance['violations'].append('لا توجد بيانات كافية للإجابة')
    
    return compliance


def get_system_status():
    """الحصول على حالة النظام الشاملة"""
    try:
        analysis = analyze_recent_interactions(100)
        policy = load_training_policy()
        
        cache_exists = os.path.exists('instance/ai_knowledge_cache.json')
        
        status = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'system_name': 'Azad Garage Manager AI',
            'version': policy.get('policy_version', 'N/A'),
            'knowledge_cache': 'loaded' if cache_exists else 'missing',
            'avg_confidence': analysis.get('avg_confidence', 0),
            'total_interactions': analysis.get('total', 0),
            'quality_score': analysis.get('quality_score', 'N/A'),
            'health': analysis.get('avg_confidence', 0) >= 70
        }
        
        return status
    
    except Exception as e:
        return {'error': str(e)}

