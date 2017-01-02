# -*- coding: utf-8 -*-
# Copyright 2015 Clouder SASU
# License LGPL-3.0 or later (http://gnu.org/licenses/lgpl.html).

from odoo import models, fields


class ClouderJob(models.Model):
    """
    Define the clouder.job,
    used to store the log and it needed link to the connector job.
    """

    _name = 'clouder.job'
    _description = 'Clouder Job'

    log = fields.Text('Log')
    name = fields.Char('Description')
    action = fields.Char('Action')
    res_id = fields.Integer('Res ID')
    model_name = fields.Char('Model')
    create_date = fields.Datetime('Created at')
    create_uid = fields.Many2one('res.users', 'By')
    start_date = fields.Datetime('Started at')
    end_date = fields.Datetime('Ended at')
    state = fields.Selection([
        ('started', 'Started'), ('done', 'Done'), ('failed', 'Failed')],
        'State', readonly=True, required=True, select=True)
    # job_id = fields.Many2one('queue.job', 'Connector Job')
    # job_state = fields.Selection([
    #     ('pending', 'Pending'),
    #     ('enqueud', 'Enqueued'),
    #     ('started', 'Started'),
    #     ('done', 'Done'),
    #     ('failed', 'Failed')], 'Job State',
    #     related='job_id.state', readonly=True)
    _order = 'create_date desc'
