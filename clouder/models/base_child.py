# -*- coding: utf-8 -*-
# Copyright 2015 Clouder SASU
# License LGPL-3.0 or later (http://gnu.org/licenses/lgpl.html).


import logging

from odoo import models, fields, api


_logger = logging.getLogger(__name__)


class ClouderBaseChild(models.Model):
    """
    Define the base.child object, used to specify the applications linked
    to a service.
    """

    _name = 'clouder.base.child'
    _inherit = ['clouder.model']
    _autodeploy = False

    base_id = fields.Many2one(
        'clouder.base', 'Base', ondelete="cascade", required=True)
    name = fields.Many2one(
        'clouder.application', 'Application', required=True)
    sequence = fields.Integer('Sequence')
    domainname = fields.Char('Name')
    domain_id = fields.Many2one('clouder.domain', 'Domain')
    service_id = fields.Many2one(
        'clouder.service', 'Service')
    child_id = fields.Many2one(
        'clouder.service', 'Service')
    backup_id = fields.Many2one('clouder.backup',
                                'Restore this backup on deployment')

    _order = 'sequence'

    @api.multi
    @api.constrains('child_id')
    def _check_child_id(self):
        if self.child_id and not self.child_id.parent_id == self:
            self.raise_error(
                "The child service is not correctly linked to the parent",
            )

    @api.multi
    def create_child(self):
        self = self.with_context(no_enqueue=True)
        self.do(
            'create_child ' + self.name.name,
            'create_child_exec', where=self.base_id)

    @api.multi
    def create_child_exec(self):
        self = self.with_context(autocreate=True)
        self.delete_child_exec()
        self.child_id = self.env['clouder.base'].create({
            'name':
                self.domainname or self.base_id.name + '-' + self.name.code,
            'domain_id':
                self.domainname and
                self.domain_id or self.base_id.domain_id.id,
            'parent_id': self.id,
            'environment_id': self.base_id.environment_id.id,
            'application_id': self.name.id,
            'service_id': self.service_id.id
        })
        if self.backup_id:
            self.backup_id.service_id = self.child_id.service_id
            self.backup_id.base_id = self.child_id
            self.backup_id.restore()

    @api.multi
    def delete_child(self):
        self.do(
            'delete_child ' + self.name.name,
            'delete_child_exec', where=self.base_id)

    @api.multi
    def delete_child_exec(self):
        self.child_id and self.child_id.unlink()
