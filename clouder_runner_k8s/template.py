# -*- coding: utf-8 -*-
##############################################################################
#
# Author: Yannick Buron
# Copyright 2015, TODAY Clouder SASU
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License with Attribution
# clause as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License with
# Attribution clause along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _
from openerp.exceptions import except_orm
import re,json

class ClouderContainer(models.Model):

    _inherit = 'clouder.container'

    @api.multi
    def deploy_frame(self):
        self.log('skip deploy container')

    @api.multi
    def hook_deploy_source(self):
        if self.image_id.name == 'img_k8s':
            return 'oondeo/hyperkube /hyperkube kubelet \
                          --pod-infra-container-image="gcr.io/google_containers/pause:3.0" \
                          --allow-privileged=true \
                          --api-servers=http://127.0.0.1:8080 \
                          --config=/etc/kubernetes/manifests \
                          --hostname-override=${ADVERTISE_IP} \
                          --network-plugin-dir=/etc/kubernetes/cni/net.d \
                          --network-plugin=cni \
                          --address=0.0.0.0 \
                          --cluster-dns=10.0.0.10 \
                          --cluster-domain=cluster.local \
                          --v=5'
        else:
            return super(ClouderContainer, self).hook_deploy_source()

class ClouderImageVersion(models.Model):
    """
    Avoid build an image if the application type if a registry.
    """

    _inherit = 'clouder.image.version'

    @api.multi
    def deploy(self):
        """
        Block the default deploy function for kubernetes.
        """

        if self.image_id.name != 'img_k8s':
            return super(ClouderImageVersion, self).deploy()
        else:
            return True

class ClouderEnvironment(models.Model):

    _inherit = 'clouder.environment'

    k8s_config = fields.Char("K8S Config")
    server_ids = fields.Many2many(
        'clouder.server', 'clouder_environment_server_rel',
        'environment_id', 'server_id', 'Servers', required=True)
    namespace = fields.Char('K8S Namespace', required=True)
    hostPath = fields.Char('Base dir for volumes')

    _sql_constraints = [
        ('namespace_uniq', 'unique(namespace)',
         'namespace must be unique!'),
    ]


    @api.model
    def _config(self,ns):
        config = \
        """{
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": "%s"
            }
        }""" % str(ns)
        return config

    @api.model
    def _create(self,vals):
        for server in vals:
            #cat <<EOF | kubectl create -f -
            server.kube_run('kube_create',self.k8s_config)

    @api.one
    def unlink(self):
        for server in self.servers:
            #cat <<EOF | kubectl create -f -
            server.kube_run('kube_delete',self.k8s_config)
        return super(ClouderEnvironment, self).unlink()

    @api.multi
    def write(self, vals):
        if vals.get("namespace"):
            vals['k8s_config'] = self._config(vals['namespace'])
        res = super(ClouderEnvironment, self).write(vals)
        if vals.get("namespace"):
            self._create(self.server_ids)
        return res

    @api.model
    def create(self,vals):
        if vals.get("namespace"):
            vals['k8s_config'] = self._config(vals['namespace'])
        res =  super(ClouderEnvironment, self).create(vals)
        if vals.get("namespace"):
            self._create(self.server_ids)
        return res

class ClouderK8sConfig(models.Model):

    _name = "clouder.k8s.config"

    config = fields.Char("Configuration")
    action = fields.Selection([('kube_create','kube_create'),('kube_delete','kube_delete'),('kube_apply','kube_apply')])
    server_id = fields.Many2one(
        'clouder.server', 'Server', ondelete="cascade", required=True)

    @api.multi
    def get_action(self):
        #self.log("get_action"+str(len(self)))
        self.ensure_one()
        return self.action+'("""%s""")' % self.config

class ClouderServer(models.Model):

    _inherit = 'clouder.server'

    # runner_command = fields.Char('Control command',default='docker exec -i kubemaster bash')
    k8s_config_ids = fields.One2many('clouder.k8s.config','server_id','Configs')


    @api.multi
    def deploy_kube(self):
        try:
            for conf in self.k8s_config_ids:
                eval("self."+conf.get_action())
                conf.unlink()
        except Exception as e:
            self.log("Error on deploy_kube")
            self.log(conf.get_action())
            self.log(str(e))
            raise e

    @api.multi
    def kube_run(self,action,obj):
        self.env['clouder.k8s.config'].create({'server_id':self.id,'config':obj,'action':action})
        self.do('environment','deploy_kube')

    @api.multi
    def kube_create(self,obj):
        # self.execute(['docker','exec','-i','kubemaster','bash'],['cat <<EOF | kubectl create -f -\n',obj,'\n','EOF\n','exit\n'])
        self.runner_id.execute([],['cat <<EOF | kubectl create -f -\n',obj,'\n','EOF\n','exit\n'])

    @api.multi
    def kube_delete(self,obj):
        # self.execute(['docker','exec','-i','kubemaster','bash'],['cat <<EOF | kubectl delete -f -\n',obj,'\n','EOF\n','exit\n'])
        self.runner_id.execute([],['cat <<EOF | kubectl delete -f -\n',obj,'\n','EOF\n','exit\n'])

    @api.multi
    def kube_apply(self,obj):
        # self.execute(['docker','exec','-i','kubemaster','bash'],['cat <<EOF | kubectl apply -f -\n',obj,'\n','EOF\n','exit\n'])
        self.runner_id.execute([],['cat <<EOF | kubectl delete -f -\n',obj,'\n','EOF\n','exit\n'])


class ClouderDeployment(models.Model):
    """
    Define deployment model that mimics deployment  config in kubernetes
    """
    _inherit = 'clouder.model'
    _name = 'clouder.deployment'

    k8s_config = fields.Char('Json Config')
    environment_id = fields.Many2one('clouder.environment', 'Environment',
                                     required=True)
    suffix = fields.Char('Suffix', required=True)
    option_ids = fields.One2many('clouder.container.option',
                                 'container_id', 'Options')
    link_ids = fields.One2many('clouder.container.link',
                               'container_id', 'Links')
    base_ids = fields.One2many('clouder.base',
                               'container_id', 'Bases')
    application_id = fields.Many2one('clouder.application',
                                     'Application', required=True)
    volume_ids = fields.One2many('clouder.container.volume',
                                 'container_id', 'Volumes')
    server_id = fields.Many2one('clouder.server', 'Server', required=True)
    ports_string = fields.Text('Ports', compute='_get_ports')
    child_ids = fields.One2many('clouder.container.child',
                                'container_id', 'Childs')
    replicas = fields.Integer('Replicas',default=1)
    labels_ids = fields.One2many('clouder.container.label',
                                 'container_id', 'Labels')
    annotations_ids = fields.One2many('clouder.container.annotation',
                                 'container_id', 'Annotations')

    @api.one
    def _get_ports(self):
        """
        Display the ports on the container lists.
        """
        self.ports_string = ''
        first = True
        for container in self.container_ids:
            if not first:
                self.ports_string += ', '
            if container.ports_string:
                self.ports_string += container.ports_string
            first = False

    @api.multi
    def onchange_application_id_vals(self, vals):
        """
        Update the options, links and some other fields when we change
        the application_id field.
        """
        if 'application_id' in vals and vals['application_id']:
            application = self.env['clouder.application'].browse(
                vals['application_id'])
            if 'server_id' not in vals or not vals['server_id']:
                vals['server_id'] = application.next_server_id.id
            if not vals['server_id']:
                servers = self.env['clouder.server'].search([])[0]
                if servers:
                    vals['server_id'] = servers[0].id
                else:
                    raise except_orm(
                        _('Data error!'),
                        _("You need to create a server before "
                          "create any deployment."))

            options = []
            # Getting sources for new options
            option_sources = {x.id: x for x in application.type_id.option_ids}
            sources_to_add = option_sources.keys()
            # Checking old options
            if 'option_ids' in vals:
                for option in vals['option_ids']:
                    # Standardizing for possible odoo x2m input
                    if isinstance(option, (list, tuple)):
                        option = {
                            'name': option[2].get('name', False),
                            'value': option[2].get('value', False)
                        }
                        # This case means we do not have an odoo recordset and need to load the link manually
                        if isinstance(option['name'], int):
                            option['name'] = self.env['clouder.application.type.option'].browse(option['name'])
                    else:
                        option = {
                            'name': getattr(option, 'name', False),
                            'value': getattr(option, 'value', False)
                        }
                    # Keeping the option if there is a match with the sources
                    if option['name'] and option['name'].id in option_sources:
                        option['source'] = option_sources[option['name'].id]

                        if option['source'].type == 'container' and option['source'].auto and \
                                not (option['source'].app_code and option['source'].app_code != application.code):
                            # Updating the default value if there is no current one set
                            options.append((0, 0, {
                                'name': option['source'].id,
                                'value': option['value'] or option['source'].get_default
                            }))

                            # Removing the source id from those to add later
                            sources_to_add.remove(option['name'].id)

            # Adding remaining options from sources
            for def_opt_key in sources_to_add:
                if option_sources[def_opt_key].type == 'container' and option_sources[def_opt_key].auto and \
                        not (
                                    option_sources[def_opt_key].app_code and
                                    option_sources[def_opt_key].app_code != application.code
                        ):
                    options.append((0, 0, {
                            'name': option_sources[def_opt_key].id,
                            'value': option_sources[def_opt_key].get_default
                    }))

            # Replacing old options
            vals['option_ids'] = options

            # Getting sources for new links
            link_sources = {x.id: x for x in application.link_ids}
            sources_to_add = link_sources.keys()
            links_to_process = []
            # Checking old links
            if 'link_ids' in vals:
                for link in vals['link_ids']:
                    # Standardizing for possible odoo x2m input
                    if isinstance(link, (list, tuple)):
                        link = {
                            'name': link[2].get('name', False),
                            'next': link[2].get('next', False)
                        }
                        # This case means we do not have an odoo recordset and need to load the link manually
                        if isinstance(link['name'], int):
                            link['name'] = self.env['clouder.application.link'].browse(link['name'])
                    else:
                        link = {
                            'name': getattr(link, 'name', False),
                            'next': getattr(link, 'next', False)
                        }
                    # Keeping the link if there is a match with the sources
                    if link['name'] and link['name'].id in link_sources:
                        link['source'] = link_sources[link['name'].id]
                        links_to_process.append(link)

                        # Remove used link from sources
                        sources_to_add.remove(link['name'].id)

            # Adding links from source
            for def_key_link in sources_to_add:
                link = {
                    'name': getattr(link_sources[def_key_link], 'name', False),
                    'next': getattr(link_sources[def_key_link], 'next', False),
                    'source': link_sources[def_key_link]
                }
                links_to_process.append(link)

            # Running algorithm to determine new links
            links = []
            for link in links_to_process:
                if link['source'].container and \
                        link['source'].auto or link['source'].make_link:
                    next_id = link['next']
                    # if 'parent_id' in vals and vals['parent_id']:
                    #     parent = self.env['clouder.container.child'].browse(
                    #         vals['parent_id'])
                    #     for parent_link in parent.container_id.link_ids:
                    #         if link['source'].name.code == parent_link.name.name.code \
                    #                 and parent_link.target:
                    #             next_id = parent_link.target.id
                    context = self.env.context
                    if not next_id and 'container_links' in context:
                        fullcode = link['source'].name.fullcode
                        if fullcode in context['container_links']:
                            next_id = context['container_links'][fullcode]
                    if not next_id:
                        next_id = link['source'].next.id
                    if not next_id:
                        target_ids = self.search([
                            ('application_id.code', '=', link['source'].name.code),
                            ('parent_id', '=', False)])
                        if target_ids:
                            next_id = target_ids[0].id
                    links.append((0, 0, {'name': link['source'].id,
                                         'target': next_id}))
            # Replacing old links
            vals['link_ids'] = links

            childs = []
            # Getting source for childs
            child_sources = {x.id: x for x in application.child_ids}
            sources_to_add = child_sources.keys()

            # Checking for old childs
            if 'child_ids' in vals:
                for child in vals['child_ids']:
                    # Standardizing for possible odoo x2m input
                    if isinstance(child, (list, tuple)):
                        child = {
                            'name': child[2].get('name', False),
                            'sequence': child[2].get('sequence', False),
                            'required': child[2].get('required', False),
                            'server_id': child[2].get('server_id', False)
                        }
                        # This case means we do not have an odoo recordset and need to load links manually
                        if isinstance(child['name'], int):
                            child['name'] = self.env['clouder.application'].browse(child['name'])
                        if isinstance(child['server_id'], int):
                            child['server_id'] = self.env['clouder.server'].browse(child['server_id'])
                    else:
                        child = {
                            'name': getattr(child, 'name', False),
                            'sequence': getattr(child, 'sequence', False),
                            'required': getattr(child, 'required', False),
                            'server_id': getattr(child, 'server_id', False)
                        }
                    if child['name'] and child['name'].id in child_sources:
                        child['source'] = child_sources[child['name'].id]
                        if child['source'].required:
                            childs.append((0, 0, {
                                'name': child['source'].id,
                                'sequence':  child['sequence'],
                                'server_id':
                                    child['server_id'] and
                                    child['server_id'].id or
                                    child['source'].next_server_id.id
                            }))

                        # Removing from sources
                        sources_to_add.remove(child['name'].id)

            # Adding remaining childs from source
            for def_child_key in sources_to_add:
                child = child_sources[def_child_key]
                if child.required:
                    childs.append((0, 0, {
                        'name': child.id,
                        'sequence': child.sequence,
                        'server_id':
                            getattr(child, 'server_id', False) and
                            child.server_id.id or
                            child.next_server_id.id
                    }))

            # Replacing old childs
            vals['child_ids'] = childs

            if 'image_id' not in vals or not vals['image_id']:
                vals['image_id'] = application.default_image_id.id

            if 'backup_ids' not in vals or not vals['backup_ids']:
                if application.container_backup_ids:
                    vals['backup_ids'] = [(6, 0, [
                        b.id for b in application.container_backup_ids])]
                else:
                    backups = self.env['clouder.container'].search([
                        ('application_id.type_id.name', '=', 'backup')])
                    if backups:
                        vals['backup_ids'] = [(6, 0, [backups[0].id])]

            vals['autosave'] = application.autosave

            vals['time_between_save'] = \
                application.container_time_between_save
            vals['save_expiration'] = \
                application.container_save_expiration
        return vals

    @api.multi
    @api.onchange('application_id')
    def onchange_application_id(self):
        vals = {
            'application_id': self.application_id.id,
            'server_id': self.server_id.id,
            'option_ids': self.option_ids,
            'link_ids': self.link_ids,
            'child_ids': self.child_ids,
            }
        vals = self.onchange_application_id_vals(vals)
        self.env['clouder.deployment.option'].search(
            [('container_id', '=', self.id)]).unlink()
        self.env['clouder.deployment.link'].search(
            [('container_id', '=', self.id)]).unlink()
        self.env['clouder.deployment.child'].search(
            [('container_id', '=', self.id)]).unlink()
        for key, value in vals.iteritems():
            setattr(self, key, value)

    @api.multi
    def hook_create(self):
        """
        Add volume/port/link/etc... if not generated through the interface
        """
        if 'autocreate' in self.env.context:
            self.onchange_application_id()
        return super(ClouderContainer, self).hook_create()

    @api.multi
    def create(self, vals):
        vals = self.onchange_application_id_vals(vals)
        res= super(ClouderContainer, self).create(vals)
        self.k8s_generate()
        return res

    # @api.multi
    # def write(self, vals):
    #     res = super(ClouderContainer, self).write(vals)
    #     self.k8s_generate()
    #     return res

    @api.one
    def unlink(self):
        """
        Override unlink method to remove all services
        and make a save before deleting a container.
        """
        self.base_ids and self.base_ids.unlink()
        self.env['clouder.save'].search([('backup_id', '=', self.id)]).unlink()
        # self.env['clouder.image.version'].search(
        #     [('registry_id', '=', self.id)]).unlink()
        # self = self.with_context(save_comment='Before unlink')
        # save = self.save_exec(no_enqueue=True)
        # if self.parent_id:
        #     self.parent_id.save_id = save
        self.server_id.kube_delete(self.k8s_config)
        return super(ClouderContainer, self).unlink()


    @api.multi
    def hook_deploy_source(self):
        """
        Hook which can be called by submodules to change the source of the image
        """
        return

    @api.multi
    def hook_deploy(self, ports, volumes):
        """
        Hook which can be called by submodules to execute commands to
        deploy a container.
        """
        return

    @api.multi
    def deploy_post(self):
        """
        Hook which can be called by submodules to execute commands after we
        deployed a container.
        """
        return

    @api.one
    def k8s_generate(self):
        containers = []
        for child in self.child_ids:
            containers.append(child.list())

        labels = [{"run":self.name}]
        for label in self.labels_ids():
                labels.append({label.name : label.value })
        """
                apiVersion: extensions/v1beta1
                kind: Deployment
                metadata:
                    name: nginx-deployment
                spec:
                replicas: 3
                template:
                metadata:
                labels:
                app: nginx
                spec:
                containers:
                - name: nginx
                image: nginx:1.7.9
                ports:
                - containerPort: 80
        """
        deployment = {
            "apiVersion": "extensions/v1beta1" ,
            "kind": "Deployment",
            "metadata": {"name": self.name,"namespace": self.environment_id.namespace },
            "spec": {
                "replicas": self.replicas,
                "template": {
                    "metadata": {
                        "labels" : labels
                    },
                    "spec": {
                        "containers": containers
                    }
                }

            }
        }

        if self.annotation_ids:
            annotations = []
            for val in self.annotation_ids:
                annotations.append({self.name:self.value})
            deployment["spec"]["template"]["metadata"]["annotations"]=annotations

        if self.volume_ids:
            volumes = []
            for vol in self.volume_ids:
                if vol.hostPath:
                    volumes.append({"name":vol.reference,
                                    "hostPath":{"path":vol.hostPath}})
                else:
                    volumes.append({"name":vol.reference,"emptyDir":{}})
            deployment["spec"]["template"]["spec"]["volumes"]=volumes

        # apiVersion: v1
        # kind: PersistentVolume
        # metadata:
        #   name: www-prod-oondeo-storage
        #   namespace: oondeo
        # spec:
        #   capacity:
        #     storage: 30Gi
        #   accessModes:
        #     - ReadWriteOnce
        #   persistentVolumeReclaimPolicy: Recycle
        #   hostPath:
        #     path: /mnt/www/oondeo
        # ---
        # kind: PersistentVolumeClaim
        # apiVersion: v1
        # metadata:
        #   name: www-oondeo-storage
        #   namespace: oondeo
        # spec:
        #   accessModes:
        #     - ReadWriteOnce
        #   volumeName: www-oondeo-storage
        #   resources:
        #     requests:
        #       storage: 8Gi


        # NetworkPolicy
        # {
        # "kind": "NetworkPolicy",
        # "metadata": {
        # "name": "pol1"
        # },
        # "spec": {
        # "allowIncoming": {
        # "from": [
        # { "pods": { "segment": "frontend" } }
        # ],
        # "toPorts": [
        # { "port": 80, "protocol": "TCP" }
        # ]
        # },
        # "podSelector": { "segment": "backend" }
        # }
        # }

        self.k8s_config = json.dumps(deployment)

    @api.multi
    def deploy(self):
        """
        Deploy the container in the server.
        """
        self = self.with_context(no_enqueue=True)
        super(ClouderContainer, self).deploy()


        self.hook_deploy(ports, volumes)

        time.sleep(3)

        self.server_id.kube_create(self.k8s_config)
        self.deploy_post()

        # self.start()

        # For shinken
        self = self.with_context(save_comment='First save')
        self.save_exec(no_enqueue=True)

        self.deploy_links()

        return

    @api.multi
    def hook_purge(self):
        """
        Hook which can be called by submodules to execute commands to
        purge a container.
        """
        return

    @api.multi
    def purge(self):
        """
        Remove the container.
        """

        childs = self.env['clouder.container.child'].search(
            [('container_id', '=', self.id)], order='sequence DESC')
        if childs:
            for child in childs:
                child.delete_child_exec()
        self.stop()
        self.hook_purge()
        self.server_id.kube_delete(self.k8s_config)
        super(ClouderContainer, self).purge()

        return

    @api.multi
    def stop(self):
        self = self.with_context(no_enqueue=True)
        self.do('stop', 'stop_exec')

    @api.multi
    def stop_exec(self):
        """
        Stop the container.
        """
        return

    @api.multi
    def start(self):
        self = self.with_context(no_enqueue=True)
        self.do('start', 'start_exec')

    @api.multi
    def start_exec(self):
        """
        Restart the container.
        """
        self.stop_exec()
        return

class ClouderContainerChild(models.Model):

    _inherit = 'clouder.container.child'


    @api.one
    def list(self):
        # name: my-nginx
        # image: nginx
        # env:
        # - name: docker-clean-up-after-yourself
        #   value: adfasdf
        # ports:
        # - containerPort: 80
        # volumeMounts:
        # - mountPath: "/usr/share/nginx/html"
        #   name: mypd
        container = {
            "name": self.container_id.name,
            "image": self.container_id.image_version_id.fullpath
        }
        if self.container_id.options:
            options = []
            for option in self.container_id.options:
                options.append({"name": option.name,"value":option.value})
            container["env"]=options
        if self.container_id.ports:
            ports = [ ]
            for port in self.container_id.ports:
                if port.udp:
                    ports.append({"containerPort": port.localport, "protocol": "UDP"})
                else:
                    ports.append({"containerPort": port.localport})
            container["ports"]=ports
        if self.container_id.volume_ids:
            volumes = []
            for vol in self.volume_ids:
                volumes.append({"name": vol.reference,"mountPath":vol.name})
            container["volumeMounts"]=volumes
        return container

#''.join(e for e in string if e.isalnum())
class ClouderContainerVolume(models.Model):

    _inherit = 'clouder.container.volume'

    @property
    def reference(self):
        string = self.container_id.name + self.name[-8:]
        return ''.join(e for e in string if e.isalnum())

class ClouderContainerAnnotation(models.Model):
    """
    Define the container.annotation object, used to define custom values
    specific to a container.
    """

    _name = 'clouder.container.annotation'

    container_id = fields.Many2one(
        'clouder.container', 'Container', ondelete="cascade", required=True)
    name = fields.Char('Name')
    value = fields.Text('Value')

    _sql_constraints = [
        ('name_uniq', 'unique(container_id,name)',
         'Annotation name must be unique per container!'),
    ]

class ClouderContainerLabel(models.Model):
    """
    Define the container.annotation object, used to define custom values
    specific to a container.
    """

    _name = 'clouder.container.label'

    container_id = fields.Many2one(
        'clouder.container', 'Container', ondelete="cascade", required=True)
    name = fields.Char('Name')
    value = fields.Text('Value')

    _sql_constraints = [
        ('name_uniq', 'unique(container_id,name)',
         'Label name must be unique per container!'),
    ]
