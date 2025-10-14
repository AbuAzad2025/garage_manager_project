# forms/archive.py - Archive Forms
# Location: /garage_manager/forms/archive.py
# Description: Archive management forms

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, SubmitField
from wtforms.validators import DataRequired, Length, Optional
from wtforms.widgets import TextArea

class ArchiveForm(FlaskForm):
    """نموذج أرشفة السجلات"""
    reason = TextAreaField(
        'سبب الأرشفة',
        validators=[DataRequired(message='سبب الأرشفة مطلوب'), Length(max=200)],
        render_kw={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'أدخل سبب أرشفة هذا السجل...'
        }
    )
    submit = SubmitField(
        'أرشفة السجل',
        render_kw={'class': 'btn btn-warning fw-bold'}
    )

class ArchiveSearchForm(FlaskForm):
    """نموذج البحث في الأرشيفات"""
    record_type = SelectField(
        'نوع السجل',
        choices=[
            ('', 'جميع الأنواع'),
            ('service_requests', 'طلبات الصيانة'),
            ('payments', 'الدفعات'),
            ('sales', 'المبيعات'),
            ('customers', 'العملاء'),
            ('products', 'المنتجات'),
            ('inventory', 'المخزون'),
            ('expenses', 'النفقات'),
            ('checks', 'الشيكات')
        ],
        render_kw={'class': 'form-select'}
    )
    
    date_from = DateField(
        'من تاريخ',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    date_to = DateField(
        'إلى تاريخ',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    search_term = StringField(
        'البحث',
        validators=[Optional()],
        render_kw={
            'class': 'form-control',
            'placeholder': 'البحث في البيانات المؤرشفة...'
        }
    )
    
    submit = SubmitField(
        'بحث',
        render_kw={'class': 'btn btn-primary fw-bold'}
    )

class BulkArchiveForm(FlaskForm):
    """نموذج الأرشفة الجماعية"""
    record_type = SelectField(
        'نوع السجل',
        choices=[
            ('service_requests', 'طلبات الصيانة'),
            ('payments', 'الدفعات'),
            ('sales', 'المبيعات'),
            ('expenses', 'النفقات'),
            ('checks', 'الشيكات')
        ],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    
    date_from = DateField(
        'من تاريخ',
        validators=[DataRequired()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    date_to = DateField(
        'إلى تاريخ',
        validators=[DataRequired()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    reason = TextAreaField(
        'سبب الأرشفة',
        validators=[DataRequired(), Length(max=200)],
        render_kw={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'أدخل سبب الأرشفة الجماعية...'
        }
    )
    
    submit = SubmitField(
        'أرشفة جماعية',
        render_kw={'class': 'btn btn-danger fw-bold'}
    )

class ArchiveRestoreForm(FlaskForm):
    """نموذج استعادة الأرشيف"""
    reason = TextAreaField(
        'سبب الاستعادة',
        validators=[DataRequired(), Length(max=200)],
        render_kw={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'أدخل سبب استعادة هذا السجل...'
        }
    )
    
    submit = SubmitField(
        'استعادة السجل',
        render_kw={'class': 'btn btn-success fw-bold'}
    )

