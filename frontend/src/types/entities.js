/** @typedef {{id:number,name:string,description:string,original_sql:string}} Sample */
/** @typedef {{id:number,name:string,sample_id:number,candidate_sql:string,status:string,snapshot_table:string|null,frozen_original_sql:string|null,frozen_candidate_sql:string|null,snapshot_row_count:number|null,snapshot_checksum:string|null,frozen_at:string|null,lease_owner:string|null,lease_until:string|null,attempts:number}} Batch */
/** @typedef {{id:number,batch_id:number,result:Object,freeze_basis:Object|null}} Evidence */
export const entityNames={sample:'SQL 样本',batch:'复核批次',evidence:'执行证据'};
