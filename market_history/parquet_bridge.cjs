const parquet=require('parquetjs-lite');
const readline=require('node:readline');
const {once}=require('node:events');
async function main(){
  const [mode,path]=process.argv.slice(2);
  if(mode==='write'){
    const fields={timestamp:{type:'INT64',compression:'GZIP'}};
    for(const key of ['open','high','low','close','volume'])fields[key]={type:'DOUBLE',compression:'GZIP'};
    const writer=await parquet.ParquetWriter.openFile(new parquet.ParquetSchema(fields),path);
    writer.setRowGroupSize(8192);
    try{for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){await writer.appendRow(JSON.parse(line));}}
    finally{await writer.close();}
  }else if(mode==='read'){
    const reader=await parquet.ParquetReader.openFile(path);
    try{const cursor=reader.getCursor();let row;
      while((row=await cursor.next())!==null){row.timestamp=Number(row.timestamp);
        if(!process.stdout.write(JSON.stringify(row)+'\n'))await once(process.stdout,'drain');}
    }finally{await reader.close();}
  }else throw Error('Expected read/write');
}
main().catch(error=>{process.stderr.write(String(error)+'\n');process.exitCode=1;});
