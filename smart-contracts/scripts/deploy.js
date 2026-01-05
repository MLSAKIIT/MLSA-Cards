const hre = require("hardhat");

async function main() {
  const name = "GameCollectible";
  const symbol = "GCARD";
  const baseURI = "ipfs://";

  const GameCollectible = await hre.ethers.getContractFactory("GameCollectible");
  const gameCollectible = await GameCollectible.deploy(name, symbol, baseURI);
  await gameCollectible.waitForDeployment();


  const address = await gameCollectible.getAddress();
  console.log("GameCollectible deployed to:", address);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
