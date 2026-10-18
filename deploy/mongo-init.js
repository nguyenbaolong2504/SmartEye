// Runs once for a NEW MongoDB volume. The web app uses readWrite, not root.
const databaseName = process.env.MONGO_INITDB_DATABASE || 'smarteye';
const username = process.env.MONGODB_USERNAME;
const password = process.env.MONGODB_PASSWORD;
if (!username || !password) throw new Error('Missing application MongoDB credentials');
const applicationDb = db.getSiblingDB(databaseName);
applicationDb.createUser({user:username,pwd:password,roles:[{role:'readWrite',db:databaseName}]});
