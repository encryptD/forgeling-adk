using GatePassService as service from '../../srv/gatepass-service';

annotate service.GatePasses with @(
  UI.SelectionFields: [
    number,
    vehicleNo,
    plant,
    status
  ],
  UI.LineItem: [
    { $Type: 'UI.DataField', Value: number },
    { $Type: 'UI.DataField', Value: vehicleNo },
    { $Type: 'UI.DataField', Value: plant },
    { $Type: 'UI.DataField', Value: status }
  ],
  UI.HeaderInfo: {
    TypeName: 'Gate Pass',
    TypeNamePlural: 'Gate Passes',
    Title: { $Type: 'UI.DataField', Value: number }
  },
  UI.FieldGroup #GeneratedGroup: {
    $Type: 'UI.FieldGroupType',
    Data: [
      { $Type: 'UI.DataField', Value: number },
      { $Type: 'UI.DataField', Value: vehicleNo },
      { $Type: 'UI.DataField', Value: plant },
      { $Type: 'UI.DataField', Value: status }
    ]
  },
  UI.Facets: [
    {
      $Type: 'UI.ReferenceFacet',
      ID: 'GeneratedFacet1',
      Label: 'General',
      Target: '@UI.FieldGroup#GeneratedGroup'
    }
  ]
);
