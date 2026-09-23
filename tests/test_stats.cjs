const test = require('node:test');
const assert = require('node:assert/strict');
const stats = require('../badger_evidence/static/stats.js');
const r = (type, value, relation='=', flags=[]) => ({measurement_type:type, normalized_value_nm:value, relation, flags});
test('chart separates endpoints and excludes bounds, flags and invalid values', () => {
  const records = [r('Ki', 10),r('IC50',100),r('Kd',20),r('Ki',30,'>'),r('Ki',40,'=', ['ambiguous']),r('Ki',null),r('Ki',Infinity),r('Ki',-1)];
  assert.deepEqual(stats.potencyValues(records, 'Ki'), [10]);
  assert.deepEqual(stats.potencyValues(records, ''), []);
});
test('median handles odd and even sample counts without mutating input', () => {
  const values = [8,2,4,6];
  assert.equal(stats.median(values),5);
  assert.deepEqual(values,[8,2,4,6]);
  assert.equal(stats.median([9,1,3]),3);
  assert.equal(stats.median([]),null);
});
