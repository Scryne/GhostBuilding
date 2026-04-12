FROM node:20-alpine

WORKDIR /app

COPY package.json ./
# package-lock.json will be copied after next app creation is confirmed
RUN npm install

COPY . .

RUN npm run build

CMD ["npm", "start"]
