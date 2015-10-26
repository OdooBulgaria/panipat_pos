from openerp import models, fields, api, _

class account_invoice(models.Model):
    _inherit = "account.invoice"
    _description = "Panipat POS Account"
    
    @api.multi
    def return_product(self):
        assert len(self) == 1, 'This option should only be used for a single id at a time.'
        if self.picking_id:
            compose_form = self.env.ref('stock.view_picking_form', False)
            return {
                'name': _('Delivery Order'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'views': [(compose_form.id, 'form')],
                'view_id': compose_form.id,                
                'res_model': 'stock.picking',
                'target': 'current',
                'context': self._context,
                'res_id':self.picking_id.id
            }        

    @api.model
    def _is_pos_invoice(self):
        if self._context.get('pos',False):
            return True
        else: False
        
    is_pos = fields.Boolean('Is POS Invoice',default=_is_pos_invoice)
    picking_id = fields.Many2one('stock.picking','Delivery Order')
    
    def _get_default_location(self, cr, uid, context=None):
        wh_obj = self.pool.get('stock.warehouse')
        user = self.pool.get('res.users').browse(cr, uid, uid, context)
        res = wh_obj.search(cr, uid, [('company_id', '=', user.company_id.id)], limit=1, context=context)
        if res and res[0]:
            return wh_obj.browse(cr, uid, res[0], context=context).lot_stock_id.id
        return False
    
    @api.one
    @api.model
    def create_picking(self):
        picking_obj = self.pool.get('stock.picking')
        partner_obj = self.pool.get('res.partner')
        move_obj = self.pool.get('stock.move')
        order = self
        print "================================service1",order.invoice_line.mapped('product_id.type')
        if all(t == 'service' for t in order.invoice_line.mapped('product_id.type')):
            return
        addr = order.partner_id and partner_obj.address_get(self._cr, self._uid, [order.partner_id.id], ['delivery']) or {}
        picking_type_id = self.pool.get('ir.model.data').get_object_reference(self._cr, self._uid, 'panipat_pos', 'picking_type_posout_panipat')[1]
        picking_type = self.pool.get('stock.picking.type').browse(self._cr,self._uid,picking_type_id,self._context)
        picking_id = False
        if picking_type:
            picking_id = picking_obj.create(self._cr, self._uid, {
                'origin': order.name,
                'partner_id': addr.get('delivery',False),
                'date_done' : order.date_invoice,
                'picking_type_id': picking_type.id,
                'company_id': order.company_id.id,
                'move_type': 'direct',
                'note': order.comment or "",
                'invoice_state': 'none',
            }, context=self._context)
            self.picking_id = picking_id
        location_id = self._get_default_location()
        if order.partner_id:
            destination_id = order.partner_id.property_stock_customer.id
        elif picking_type:
            if not picking_type.default_location_dest_id:
                raise osv.except_osv(_('Error!'), _('Missing source or destination location for picking type %s. Please configure those fields and try again.' % (picking_type.name,)))
            destination_id = picking_type.default_location_dest_id.id
        else:
            destination_id = partner_obj.default_get(self._cr, self._uid, ['property_stock_customer'], context=self._context)['property_stock_customer']

        move_list = []
        for line in order.invoice_line:
            if line.product_id and line.product_id.type == 'service':
                continue

            move_list.append(move_obj.create(self._cr, self._uid, {
                'name': line.name,
                'product_uom': line.product_id.uom_id.id,
                'product_uos': line.product_id.uom_id.id,
                'picking_id': picking_id,
                'picking_type_id': picking_type.id, 
                'product_id': line.product_id.id,
                'product_uos_qty': abs(line.quantity),
                'product_uom_qty': abs(line.quantity),
                'state': 'draft',
                'location_id': location_id if line.quantity >= 0 else destination_id,
                'location_dest_id': destination_id if line.quantity >= 0 else location_id,
            }, context=self._context))
            
        if picking_id:
            picking_obj.action_confirm(self._cr, self._uid, [picking_id], context=self._context)
            picking_obj.force_assign(self._cr, self._uid, [picking_id], context=self._context)
            picking_obj.action_done(self._cr, self._uid, [picking_id], context=self._context)
        elif move_list:
            move_obj.action_confirm(self._cr, self._uid, move_list, context=self._context)
            move_obj.force_assign(self._cr,self._uid, move_list, context=self._context)
            move_obj.action_done(self._cr, self._uid, move_list, context=self._context)
        return True

        