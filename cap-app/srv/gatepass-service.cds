using my.cap as db from '../db/schema';

service GatePassService @(path: 'gate-pass') {
  entity GatePasses as projection on db.GatePass;
}

annotate GatePassService.GatePasses with {
  plant @mandatory;
};
