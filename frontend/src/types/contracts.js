/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string,ingestion_batch_id:number,contract_id:number,contract_version:number}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,source_version:string,version:number,column_mapping:Object,units:Object,active:boolean,checksum:string}} IngestionContract */
/** @typedef {{id:number,name:string,source:string,source_version:string,raw_checksum:string,raw_revision:number,status:string,errors:Array,error_count:number,contract_version:number,normalized_rows:number,published_dataset_id:number,validated_attempt_id:number}} IngestionBatch */
export {};
