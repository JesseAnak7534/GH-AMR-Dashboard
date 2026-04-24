"""
Scheduled Reports Module for AMR Surveillance Dashboard.
Handles automatic report generation and email delivery to stakeholders.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from dotenv import load_dotenv

from . import db as _db

# Load environment variables
load_dotenv()


def _connect():
    """Return a Postgres connection via the shared backend."""
    return _db.get_connection()


class ReportFrequency(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ReportType(Enum):
    SUMMARY = "summary"           # General summary report
    RESISTANCE = "resistance"     # Resistance rates report
    ANTIBIOGRAM = "antibiogram"   # Antibiogram report
    OUTBREAK = "outbreak"         # Outbreak detection report
    ALERTS = "alerts"             # Alerts summary
    WHONET = "whonet"             # WHONET export
    TREND = "trend"               # Trend analysis report


@dataclass
class ScheduledReport:
    """Represents a scheduled report configuration."""
    id: int = 0
    name: str = ""
    report_type: ReportType = ReportType.SUMMARY
    frequency: ReportFrequency = ReportFrequency.WEEKLY
    recipients: List[str] = field(default_factory=list)
    filters: Dict = field(default_factory=dict)  # lab_name, organism, date_range, etc.
    day_of_week: int = 0  # 0=Monday, 6=Sunday (for weekly)
    day_of_month: int = 1  # 1-28 (for monthly)
    hour: int = 8  # Hour to send (24-hour format)
    minute: int = 0
    is_active: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""


class ReportScheduler:
    """Manages scheduled reports and their execution."""
    
    def __init__(self, db_path: str = "db/amr_data.db"):
        # db_path retained for API compatibility; Postgres connection comes
        # from the shared src.db backend, not this string.
        self.db_path = db_path
        self._scheduler_thread: Optional[threading.Thread] = None
        self._running = False
        _db.init_database()
    
    def create_schedule(self, report: ScheduledReport) -> int:
        """Create a new scheduled report."""
        conn = _connect()
        cursor = conn.cursor()
        
        # Calculate next run time
        next_run = self._calculate_next_run(report)
        
        cursor.execute('''
            INSERT INTO scheduled_reports
            (name, report_type, frequency, recipients, filters, day_of_week,
             day_of_month, hour, minute, is_active, next_run, created_at, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            report.name,
            report.report_type.value,
            report.frequency.value,
            json.dumps(report.recipients),
            json.dumps(report.filters),
            report.day_of_week,
            report.day_of_month,
            report.hour,
            report.minute,
            1 if report.is_active else 0,
            next_run.isoformat() if next_run else None,
            report.created_at.isoformat(),
            report.created_by
        ))

        schedule_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        
        return schedule_id
    
    def update_schedule(self, report: ScheduledReport) -> bool:
        """Update an existing scheduled report."""
        conn = _connect()
        cursor = conn.cursor()
        
        next_run = self._calculate_next_run(report)
        
        cursor.execute('''
            UPDATE scheduled_reports
            SET name=%s, report_type=%s, frequency=%s, recipients=%s, filters=%s,
                day_of_week=%s, day_of_month=%s, hour=%s, minute=%s, is_active=%s, next_run=%s
            WHERE id=%s
        ''', (
            report.name,
            report.report_type.value,
            report.frequency.value,
            json.dumps(report.recipients),
            json.dumps(report.filters),
            report.day_of_week,
            report.day_of_month,
            report.hour,
            report.minute,
            1 if report.is_active else 0,
            next_run.isoformat() if next_run else None,
            report.id
        ))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        
        return success
    
    def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a scheduled report."""
        conn = _connect()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM scheduled_reports WHERE id=%s', (schedule_id,))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        
        return success
    
    def get_schedule(self, schedule_id: int) -> Optional[ScheduledReport]:
        """Get a scheduled report by ID."""
        conn = _connect()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM scheduled_reports WHERE id=%s', (schedule_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_schedule(row)
        return None
    
    def get_all_schedules(self, active_only: bool = False) -> List[ScheduledReport]:
        """Get all scheduled reports."""
        conn = _connect()
        cursor = conn.cursor()
        
        if active_only:
            cursor.execute('SELECT * FROM scheduled_reports WHERE is_active=1 ORDER BY next_run')
        else:
            cursor.execute('SELECT * FROM scheduled_reports ORDER BY created_at DESC')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_schedule(row) for row in rows]
    
    def _row_to_schedule(self, row) -> ScheduledReport:
        """Convert database row to ScheduledReport object."""
        return ScheduledReport(
            id=row[0],
            name=row[1],
            report_type=ReportType(row[2]),
            frequency=ReportFrequency(row[3]),
            recipients=json.loads(row[4]) if row[4] else [],
            filters=json.loads(row[5]) if row[5] else {},
            day_of_week=row[6],
            day_of_month=row[7],
            hour=row[8],
            minute=row[9],
            is_active=bool(row[10]),
            last_run=datetime.fromisoformat(row[11]) if row[11] else None,
            next_run=datetime.fromisoformat(row[12]) if row[12] else None,
            created_at=datetime.fromisoformat(row[13]) if row[13] else datetime.now(),
            created_by=row[14] or ""
        )
    
    def _calculate_next_run(self, report: ScheduledReport) -> Optional[datetime]:
        """Calculate the next run time for a scheduled report."""
        now = datetime.now()
        
        if report.frequency == ReportFrequency.DAILY:
            next_run = now.replace(hour=report.hour, minute=report.minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
                
        elif report.frequency == ReportFrequency.WEEKLY:
            days_ahead = report.day_of_week - now.weekday()
            if days_ahead < 0:  # Target day already passed this week
                days_ahead += 7
            elif days_ahead == 0:
                # Check if time has passed today
                target_time = now.replace(hour=report.hour, minute=report.minute, second=0, microsecond=0)
                if now >= target_time:
                    days_ahead = 7
            
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=report.hour, minute=report.minute, second=0, microsecond=0)
            
        elif report.frequency == ReportFrequency.BIWEEKLY:
            days_ahead = report.day_of_week - now.weekday()
            if days_ahead <= 0:
                days_ahead += 14
            
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=report.hour, minute=report.minute, second=0, microsecond=0)
            
        elif report.frequency == ReportFrequency.MONTHLY:
            # Try current month first
            try:
                next_run = now.replace(day=report.day_of_month, hour=report.hour, minute=report.minute, second=0, microsecond=0)
                if next_run <= now:
                    # Move to next month
                    if now.month == 12:
                        next_run = next_run.replace(year=now.year + 1, month=1)
                    else:
                        next_run = next_run.replace(month=now.month + 1)
            except ValueError:
                # Day doesn't exist in month, use last day
                next_month = now.month + 1 if now.month < 12 else 1
                next_year = now.year if now.month < 12 else now.year + 1
                next_run = datetime(next_year, next_month, 1, report.hour, report.minute) - timedelta(days=1)
                
        elif report.frequency == ReportFrequency.QUARTERLY:
            quarter = (now.month - 1) // 3 + 1
            quarter_start_month = (quarter - 1) * 3 + 1
            next_quarter_month = quarter_start_month + 3
            
            if next_quarter_month > 12:
                next_quarter_month = 1
                next_year = now.year + 1
            else:
                next_year = now.year
            
            next_run = datetime(next_year, next_quarter_month, report.day_of_month, report.hour, report.minute)
        
        else:
            next_run = now + timedelta(days=1)
        
        return next_run
    
    def get_due_schedules(self) -> List[ScheduledReport]:
        """Get all schedules that are due for execution."""
        now = datetime.now()
        schedules = self.get_all_schedules(active_only=True)
        
        return [s for s in schedules if s.next_run and s.next_run <= now]
    
    def mark_schedule_run(self, schedule_id: int, success: bool, error_message: str = None):
        """Mark a schedule as having been run and update next run time."""
        conn = _connect()
        cursor = conn.cursor()
        
        # Get current schedule
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            conn.close()
            return
        
        # Calculate next run
        next_run = self._calculate_next_run(schedule)
        now = datetime.now()
        
        # Update schedule
        cursor.execute('''
            UPDATE scheduled_reports
            SET last_run=%s, next_run=%s
            WHERE id=%s
        ''', (now.isoformat(), next_run.isoformat() if next_run else None, schedule_id))
        
        # Log to history
        cursor.execute('''
            INSERT INTO report_history (schedule_id, report_type, run_time, status, recipients, error_message)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            schedule_id,
            schedule.report_type.value,
            now.isoformat(),
            'success' if success else 'failed',
            json.dumps(schedule.recipients),
            error_message
        ))
        
        conn.commit()
        conn.close()
    
    def get_report_history(self, schedule_id: Optional[int] = None, limit: int = 50) -> List[Dict]:
        """Get report execution history."""
        conn = _connect()
        cursor = conn.cursor()
        
        if schedule_id:
            cursor.execute('''
                SELECT h.*, s.name FROM report_history h
                LEFT JOIN scheduled_reports s ON h.schedule_id = s.id
                WHERE h.schedule_id=%s
                ORDER BY h.run_time DESC LIMIT %s
            ''', (schedule_id, limit))
        else:
            cursor.execute('''
                SELECT h.*, s.name FROM report_history h
                LEFT JOIN scheduled_reports s ON h.schedule_id = s.id
                ORDER BY h.run_time DESC LIMIT %s
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for row in rows:
            history.append({
                'id': row[0],
                'schedule_id': row[1],
                'report_type': row[2],
                'run_time': row[3],
                'status': row[4],
                'recipients': json.loads(row[5]) if row[5] else [],
                'error_message': row[6],
                'file_path': row[7],
                'schedule_name': row[8] if len(row) > 8 else None
            })
        
        return history


class ReportGenerator:
    """Generates various report types for scheduling."""
    
    def __init__(self, db_path: str = "db/amr_data.db"):
        self.db_path = db_path
    
    def generate_summary_report(self, filters: Dict = None) -> Dict:
        """Generate a summary report."""
        samples_df = _db.get_all_samples()
        ast_df = _db.get_all_ast_results()
        
        # Apply filters if provided
        if filters:
            if 'lab_name' in filters and filters['lab_name']:
                samples_df = samples_df[samples_df['lab_name'] == filters['lab_name']]
            if 'date_from' in filters and filters['date_from']:
                samples_df = samples_df[samples_df['collection_date'] >= filters['date_from']]
            if 'date_to' in filters and filters['date_to']:
                samples_df = samples_df[samples_df['collection_date'] <= filters['date_to']]
        
        # Merge data
        merged = ast_df.merge(samples_df, on='sample_id', how='inner')
        
        # Calculate statistics
        total_samples = len(samples_df)
        total_tests = len(ast_df)
        
        resistance_rate = 0
        if not merged.empty:
            resistance_rate = (merged['result'] == 'R').sum() / len(merged) * 100
        
        # Top organisms
        top_organisms = merged['organism'].value_counts().head(10).to_dict() if not merged.empty else {}
        
        # Top resistance
        if not merged.empty:
            resistant = merged[merged['result'] == 'R']
            top_resistance = resistant.groupby(['organism', 'antibiotic']).size().nlargest(10).to_dict()
        else:
            top_resistance = {}
        
        return {
            'generated_at': datetime.now().isoformat(),
            'filters_applied': filters,
            'summary': {
                'total_samples': total_samples,
                'total_tests': total_tests,
                'overall_resistance_rate': round(resistance_rate, 2),
                'unique_organisms': merged['organism'].nunique() if not merged.empty else 0,
                'unique_antibiotics': merged['antibiotic'].nunique() if not merged.empty else 0
            },
            'top_organisms': top_organisms,
            'top_resistance_combinations': top_resistance
        }
    
    def generate_resistance_report(self, filters: Dict = None) -> Dict:
        """Generate detailed resistance rates report."""
        samples_df = _db.get_all_samples()
        ast_df = _db.get_all_ast_results()
        
        merged = ast_df.merge(samples_df, on='sample_id', how='inner')
        
        if filters:
            if 'lab_name' in filters and filters['lab_name']:
                merged = merged[merged['lab_name'] == filters['lab_name']]
        
        if merged.empty:
            return {'error': 'No data available', 'rates': pd.DataFrame()}
        
        # Calculate resistance rates by organism-antibiotic
        rates = merged.groupby(['organism', 'antibiotic']).apply(
            lambda x: pd.Series({
                'total': len(x),
                'resistant': (x['result'] == 'R').sum(),
                'susceptible': (x['result'] == 'S').sum(),
                'intermediate': (x['result'] == 'I').sum(),
                'resistance_rate': (x['result'] == 'R').sum() / len(x) * 100
            })
        ).reset_index()
        
        return {
            'generated_at': datetime.now().isoformat(),
            'rates': rates.to_dict('records'),
            'high_resistance': rates[rates['resistance_rate'] >= 50].to_dict('records'),
            'critical_alerts': rates[rates['resistance_rate'] >= 80].to_dict('records')
        }
    
    def report_to_html(self, report_data: Dict, report_type: ReportType) -> str:
        """Convert report data to HTML format for email."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #0d9488, #0891b2); color: white; padding: 20px; border-radius: 10px 10px 0 0; margin: -30px -30px 20px -30px; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .header p {{ margin: 5px 0 0 0; opacity: 0.9; }}
                .section {{ margin: 20px 0; padding: 15px; background: #f8fafc; border-radius: 8px; }}
                .section h3 {{ color: #0f766e; margin-top: 0; }}
                .stat-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; }}
                .stat-card {{ background: white; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #e2e8f0; }}
                .stat-value {{ font-size: 28px; font-weight: bold; color: #0d9488; }}
                .stat-label {{ color: #64748b; font-size: 12px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
                th {{ background: #0f766e; color: white; }}
                tr:nth-child(even) {{ background: #f8fafc; }}
                .alert-high {{ background: #fef2f2; color: #dc2626; }}
                .alert-medium {{ background: #fffbeb; color: #d97706; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 12px; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>AMR Surveillance Report</h1>
                    <p>{report_type.value.title()} Report - Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                </div>
        """
        
        if report_type == ReportType.SUMMARY:
            summary = report_data.get('summary', {})
            html += f"""
                <div class="stat-grid">
                    <div class="stat-card">
                        <div class="stat-value">{summary.get('total_samples', 0):,}</div>
                        <div class="stat-label">Total Samples</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{summary.get('total_tests', 0):,}</div>
                        <div class="stat-label">Total Tests</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{summary.get('overall_resistance_rate', 0):.1f}%</div>
                        <div class="stat-label">Resistance Rate</div>
                    </div>
                </div>
                
                <div class="section">
                    <h3>Top Organisms</h3>
                    <table>
                        <tr><th>Organism</th><th>Count</th></tr>
            """
            for org, count in report_data.get('top_organisms', {}).items():
                html += f"<tr><td>{org}</td><td>{count}</td></tr>"
            html += "</table></div>"
        
        elif report_type == ReportType.RESISTANCE:
            high_resistance = report_data.get('high_resistance', [])
            html += """
                <div class="section">
                    <h3>High Resistance Alerts (≥50%)</h3>
                    <table>
                        <tr><th>Organism</th><th>Antibiotic</th><th>Rate</th><th>N</th></tr>
            """
            for item in high_resistance[:15]:
                alert_class = 'alert-high' if item.get('resistance_rate', 0) >= 80 else 'alert-medium'
                html += f"""<tr class="{alert_class}">
                    <td>{item.get('organism', '')}</td>
                    <td>{item.get('antibiotic', '')}</td>
                    <td>{item.get('resistance_rate', 0):.1f}%</td>
                    <td>{item.get('total', 0)}</td>
                </tr>"""
            html += "</table></div>"
        
        html += """
                <div class="footer">
                    <p>This is an automated report from ICBB-AMRSS (ICBB AMR Surveillance System).</p>
                    <p>Ghana Food Safety Authority</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html


class EmailSender:
    """Handles email delivery for scheduled reports."""
    
    def __init__(self, smtp_server: str = None, smtp_port: int = None,
                 username: str = None, password: str = None, use_tls: bool = True):
        # Reload dotenv to get latest values
        load_dotenv()
        
        self.smtp_server = smtp_server or os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(smtp_port or os.environ.get('SMTP_PORT', 587))
        self.username = username or os.environ.get('SMTP_USERNAME', '')
        self.password = password or os.environ.get('SMTP_PASSWORD', '')
        self.from_name = os.environ.get('SMTP_FROM_NAME', 'ICBB-AMRSS')
        self.use_tls = use_tls
    
    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return bool(self.smtp_server and self.username and self.password and 
                    self.password != 'your_app_password_here')
    
    def get_config_status(self) -> Dict:
        """Get email configuration status for display."""
        return {
            'configured': self.is_configured(),
            'smtp_server': self.smtp_server,
            'smtp_port': self.smtp_port,
            'username': self.username[:3] + '***' if self.username else 'Not set',
            'password_set': bool(self.password and self.password != 'your_app_password_here')
        }
    
    def test_connection(self) -> Dict:
        """Test the SMTP connection."""
        if not self.is_configured():
            return {'success': False, 'message': 'Email not configured. Please update .env file with valid SMTP credentials.'}
        
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.quit()
            return {'success': True, 'message': 'SMTP connection successful!'}
        except smtplib.SMTPAuthenticationError:
            return {'success': False, 'message': 'Authentication failed. Check username and password.'}
        except smtplib.SMTPConnectError:
            return {'success': False, 'message': f'Could not connect to {self.smtp_server}:{self.smtp_port}'}
        except Exception as e:
            return {'success': False, 'message': f'Connection error: {str(e)}'}
    
    def send_report(self, recipients: List[str], subject: str, 
                   html_content: str, attachments: List[Dict] = None) -> Dict:
        """
        Send a report email.
        
        Args:
            recipients: List of email addresses
            subject: Email subject
            html_content: HTML body content
            attachments: List of dicts with 'filename' and 'data' (bytes)
        
        Returns:
            Dict with 'success' and 'message' keys
        """
        if not recipients:
            return {'success': False, 'message': 'No recipients specified'}
        
        if not self.is_configured():
            return {'success': False, 'message': 'Email not configured. Update .env with SMTP credentials.'}
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.from_name} <{self.username}>"
        msg['To'] = ', '.join(recipients)
        
        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Add attachments
        if attachments:
            for attachment in attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment['data'])
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{attachment["filename"]}"'
                )
                msg.attach(part)
        
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.username, recipients, msg.as_string())
            server.quit()
            return {'success': True, 'message': f'Email sent successfully to {len(recipients)} recipient(s)'}
        except smtplib.SMTPAuthenticationError:
            return {'success': False, 'message': 'SMTP Authentication failed. Check credentials.'}
        except smtplib.SMTPRecipientsRefused:
            return {'success': False, 'message': 'Recipients refused. Check email addresses.'}
        except Exception as e:
            return {'success': False, 'message': f'Failed to send: {str(e)}'}


def get_schedule_summary() -> Dict:
    """Get a summary of all scheduled reports for dashboard display."""
    scheduler = ReportScheduler()
    schedules = scheduler.get_all_schedules()
    history = scheduler.get_report_history(limit=20)
    
    active_count = sum(1 for s in schedules if s.is_active)
    upcoming = [s for s in schedules if s.is_active and s.next_run]
    upcoming.sort(key=lambda x: x.next_run)
    
    return {
        'total_schedules': len(schedules),
        'active_schedules': active_count,
        'next_upcoming': [
            {
                'name': s.name,
                'type': s.report_type.value,
                'next_run': s.next_run.isoformat() if s.next_run else None,
                'frequency': s.frequency.value
            }
            for s in upcoming[:5]
        ],
        'recent_history': history[:10],
        'success_rate': sum(1 for h in history if h['status'] == 'success') / len(history) * 100 if history else 100
    }
