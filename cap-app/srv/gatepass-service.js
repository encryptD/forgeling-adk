const cds = require('@sap/cds')

module.exports = class GatePassService extends cds.ApplicationService {
  init() {
    this.before('CREATE', 'GatePasses', (req) => {
      const data = req.data || {}

      const vehicleNo = data.vehicleNo
      if (!vehicleNo || String(vehicleNo).trim() === '') {
        req.error(400, 'Vehicle number is required', 'vehicleNo')
      }

      const plant = data.plant
      if (!plant || String(plant).trim() === '') {
        req.error(400, 'Plant is required', 'plant')
      }
    })

    return super.init()
  }
}
