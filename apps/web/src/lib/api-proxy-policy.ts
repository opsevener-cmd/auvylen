const id = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const account = /^v1\/(auth\/(csrf|register|login|logout|me)|account|redeem|credit-products|credit-analyses(?:\/[0-9a-f-]+(?:\/result)?)?)$/;
const research = new RegExp(`^v1/research/(status|aesthetic/(?:status|analyses(?:/${id}(?:/delete)?)?)|jobs(?:/${id}(?:/cancel)?)?|preferences/(models(?:/${id}/(?:edit|delete))?|extractors|train|predict|projects|datasets(?:/${id}(?:/(edit|delete|pairs|readiness|images(?:/${id}/(content|edit|rating|delete))?))?)?))$`);
const owner = /^v1\/owner\/(overview|users(?:\/usr_[0-9a-f]{32}\/(status|research|credits))?|batches(?:\/batch_[0-9a-f]{32}\/disable)?|jobs|audit)$/;
export function allowedApiPath(path: string): boolean {
  return account.test(path) || research.test(path) || owner.test(path);
}
