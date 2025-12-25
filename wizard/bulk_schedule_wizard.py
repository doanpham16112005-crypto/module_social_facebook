from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class BulkScheduleWizard(models.TransientModel):
    _name = 'social.bulk.schedule.wizard'
    _description = 'Bulk Post Scheduler Wizard'

    account_ids = fields.Many2many('social.account', string='Facebook Pages', required=True,
                                    domain=[('platform', '=', 'facebook'), ('state', '=', 'connected')])
    post_template_ids = fields.Many2many('social.post.template', string='Post Templates')
    
    schedule_type = fields.Selection([
        ('specific', 'Specific Dates'),
        ('recurring', 'Recurring Schedule'),
    ], string='Schedule Type', default='specific', required=True)
    
    start_date = fields.Datetime(string='Start Date', default=lambda self: fields.Datetime.now() + timedelta(hours=1))
    end_date = fields.Datetime(string='End Date')
    time_slots = fields.Text(string='Time Slots', default='09:00\n12:00\n15:00\n18:00')
    
    frequency = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string='Frequency', default='daily')
    
    interval = fields.Integer(string='Every', default=1)
    
    weekday_monday = fields.Boolean(string='Monday', default=True)
    weekday_tuesday = fields.Boolean(string='Tuesday', default=True)
    weekday_wednesday = fields.Boolean(string='Wednesday', default=True)
    weekday_thursday = fields.Boolean(string='Thursday', default=True)
    weekday_friday = fields.Boolean(string='Friday', default=True)
    weekday_saturday = fields.Boolean(string='Saturday', default=False)
    weekday_sunday = fields.Boolean(string='Sunday', default=False)
    
    day_of_month = fields.Integer(string='Day of Month', default=1)
    posting_times = fields.Text(string='Daily Posting Times', default='09:00\n15:00')
    duration_days = fields.Integer(string='Duration (Days)', default=30)
    
    content_rotation = fields.Selection([
        ('sequential', 'Sequential'),
        ('random', 'Random'),
    ], string='Content Rotation', default='sequential')
    
    preview_count = fields.Integer(string='Posts to Create', compute='_compute_preview_count')
    
    @api.depends('account_ids', 'post_template_ids', 'schedule_type', 'start_date', 'end_date', 'duration_days')
    def _compute_preview_count(self):
        for wizard in self:
            try:
                schedule = wizard._generate_schedule()
                wizard.preview_count = len(schedule) * len(wizard.account_ids)
            except:
                wizard.preview_count = 0
    
    def _get_selected_weekdays(self):
        self.ensure_one()
        weekdays = []
        if self.weekday_monday: weekdays.append(0)
        if self.weekday_tuesday: weekdays.append(1)
        if self.weekday_wednesday: weekdays.append(2)
        if self.weekday_thursday: weekdays.append(3)
        if self.weekday_friday: weekdays.append(4)
        if self.weekday_saturday: weekdays.append(5)
        if self.weekday_sunday: weekdays.append(6)
        return weekdays
    
    def _parse_time_slots(self, time_text):
        times = []
        for line in (time_text or '').split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                hour, minute = map(int, line.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    times.append((hour, minute))
            except:
                pass
        return times if times else [(9, 0)]
    
    def _generate_schedule(self):
        self.ensure_one()
        schedule = []
        
        if not self.start_date:
            return schedule
        
        if self.schedule_type == 'specific':
            current = self.start_date
            end = self.end_date or (self.start_date + timedelta(days=30))
            times = self._parse_time_slots(self.time_slots)
            
            while current <= end:
                for hour, minute in times:
                    scheduled_time = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if scheduled_time > fields.Datetime.now():
                        schedule.append(scheduled_time)
                current += timedelta(days=1)
        else:
            current = self.start_date
            end_date = current + timedelta(days=self.duration_days)
            times = self._parse_time_slots(self.posting_times)
            selected_weekdays = self._get_selected_weekdays()
            
            while current <= end_date:
                should_post = False
                if self.frequency == 'daily':
                    should_post = True
                elif self.frequency == 'weekly':
                    should_post = current.weekday() in selected_weekdays
                elif self.frequency == 'monthly':
                    should_post = current.day == self.day_of_month
                
                if should_post:
                    for hour, minute in times:
                        scheduled_time = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        if scheduled_time > fields.Datetime.now():
                            schedule.append(scheduled_time)
                
                current += timedelta(days=1)
        
        return sorted(schedule)
    
    def action_schedule_posts(self):
        self.ensure_one()
        
        if not self.account_ids:
            raise UserError(_('Please select at least one Facebook Page!'))
        if not self.post_template_ids:
            raise UserError(_('Please select at least one post template!'))
        
        schedule = self._generate_schedule()
        if not schedule:
            raise UserError(_('No valid schedule dates found!'))
        
        created_posts = self.env['social.post']
        template_index = 0
        templates_list = list(self.post_template_ids)
        
        for scheduled_time in schedule:
            template = templates_list[template_index % len(templates_list)]
            template_index += 1
            
            for account in self.account_ids:
                post = self.env['social.post'].create({
                    'account_id': account.id,
                    'content': template.content,
                    'post_type': 'scheduled',
                    'scheduled_date': scheduled_time,
                    'state': 'scheduled',
                })
                created_posts |= post
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Successfully scheduled %d posts!') % len(created_posts),
                'type': 'success',
                'sticky': False,
            }
        }
