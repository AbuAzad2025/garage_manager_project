# File: routes/reports.py

import json, io, pandas as pd
from datetime import datetime
from flask import Blueprint, render_template, request, send_file, jsonify
from flask_login import login_required, current_user
from extensions import db
from forms import UniversalReportForm
from utils import permission_required
from reports import advanced_report
from models import AuditLog

reports_bp = Blueprint(
    'reports',
    __name__,
    url_prefix='/reports',
    template_folder='../templates/reports'
)

def log_report_generation(user_id, model, filters, summary):
    db.session.add(AuditLog(
        user_id=user_id,
        action='generate_report',
        new_data=json.dumps(
            {'model': model, 'filters': filters, 'summary': summary},
            ensure_ascii=False
        )
    ))
    db.session.commit()

@reports_bp.route('/', endpoint='index')
@login_required
@permission_required('view_reports')
def index():
    model_names = ['Customer', 'Sale', 'Expense', 'ServiceRequest', 'OnlinePreOrder']
    return render_template('reports/index.html', model_names=model_names)

@reports_bp.route('/dynamic', methods=['GET', 'POST'], endpoint='dynamic_report')
@login_required
@permission_required('view_reports')
def dynamic_report():
    form = UniversalReportForm()
    data, summary, columns = [], {}, []
    if form.validate_on_submit():
        try:
            result = advanced_report(
                model=form.get_model(),
                date_field=form.date_field.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                filters=form.get_filters(),
                columns=form.selected_fields.data,
                aggregates=form.get_aggregates()
            )
            data, summary = result['data'], result['summary']
            columns = list(data[0].keys()) if data else []
            log_report_generation(
                current_user.id,
                form.table.data,
                form.get_filters(),
                summary
            )
            if 'export_excel' in request.form:
                df = pd.DataFrame(data)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Data')
                    if summary:
                        pd.DataFrame([summary]).to_excel(
                            writer, index=False, sheet_name='Summary'
                        )
                output.seek(0)
                return send_file(
                    output,
                    download_name=f"report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                    as_attachment=True
                )
        except Exception as e:
            return render_template(
                'reports/dynamic_report.html',
                form=form,
                error=str(e)
            )
    return render_template(
        'reports/dynamic_report.html',
        form=form,
        data=data,
        summary=summary,
        columns=columns
    )

@reports_bp.route('/api/model_fields')
@login_required
@permission_required('view_reports')
def api_model_fields():
    try:
        return jsonify(
            UniversalReportForm.get_model_metadata(
                request.args.get('model')
            )
        )
    except Exception:
        return jsonify([])
