# -*- coding: utf-8 -*-
# Copyright 2015 Clouder SASU
# License LGPL-3.0 or later (http://gnu.org/licenses/lgpl.html).

from odoo import models, fields, api


import logging
_logger = logging.getLogger(__name__)


class ClouderServiceLink(models.Model):
    """
    Define the service.link object, used to specify the applications linked
    to a service.
    """

    _name = 'clouder.service.link'
    _inherit = ['clouder.model']
    _autodeploy = False

    service_id = fields.Many2one(
        'clouder.service', 'Service', ondelete="cascade", required=True)
    name = fields.Many2one(
        'clouder.application', 'Application', required=True)
    target = fields.Many2one('clouder.service', 'Target')
    required = fields.Boolean('Required?')
    auto = fields.Boolean('Auto?')
    make_link = fields.Boolean('Make docker link?')
    deployed = fields.Boolean('Deployed?', readonly=True)

    @api.multi
    @api.constrains('service_id')
    def _check_required(self):
        """
        Check that we specify a value for the link
        if this link is required.
        """
        if self.required and not self.target \
                and not self.service_id.child_ids:
            self.raise_error(
                'You need to specify a link to '
                '"%s" for the service "%s".',
                self.name.name, self.service_id.name,
            )

    @api.multi
    def deploy_link(self):
        """
        Hook which can be called by submodules to execute commands when we
        deploy a link.
        """
        self.purge_link()
        self.deployed = True
        return

    @api.multi
    def purge_link(self):
        """
        Hook which can be called by submodules to execute commands when we
        purge a link.
        """
        self.deployed = False
        return

    @api.multi
    def control(self):
        """
        Make the control to know if we can launch the deploy/purge.
        """
        if self.service_id.child_ids:
            self.log('The service has children, skipping deploy link')
            return False
        if not self.target:
            self.log('The target isnt configured in the link, '
                     'skipping deploy link')
            return False
        return True

    @api.multi
    def deploy_(self):
        self = self.with_context(no_enqueue=True)
        self.do(
            'deploy_link ' + self.name.name,
            'deploy_exec', where=self.service_id)

    @api.multi
    def deploy_exec(self):
        """
        Control and call the hook to deploy the link.
        """
        self.control() and self.deploy_link()

    @api.multi
    def purge_(self):
        self = self.with_context(no_enqueue=True)
        self.do(
            'purge_link ' + self.name.name,
            'purge_exec', where=self.service_id)

    @api.multi
    def purge_exec(self):
        """
        Control and call the hook to purge the link.
        """
        self.control() and self.purge_link()
